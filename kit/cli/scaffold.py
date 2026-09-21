"""Writing a profile into place: vault, SOUL, prompts, hook and scheduled jobs."""
from __future__ import annotations
import companion_platform as cp
import companion_render as cr
import datetime as dt
import functools
import json
import os
import pathlib
import re
import shutil
import subprocess
import uuid
import companion_wizard as wiz
from .common import KIT, T, _read_jobs, edit_count, load_manifest, mapping, print, write
from .questions import ask, confirm

# Editor and sync droppings that should never be committed alongside a vault, and
# are worth listing before the tools that make them have run even once — a rule
# added after the first commit is a rule added after the mess.
VAULT_IGNORES=('.obsidian/','.trash/','.DS_Store','Thumbs.db','.stfolder/','.stversions/',
               '*.tmp','*.tmp*','*.swp','*.lock','**/companion-life/.inputs/',
               '**/image-timeline/','creations/**/*.png','creations/**/*.webp','creations/**/*.jpg')
def ensure_vault_gitignore(vault,report=None):
    """Add the vault ignores without disturbing anything already there. Written
    whether or not the vault is a git repository yet: the point is that it is
    already correct on the day somebody runs git init."""
    path=pathlib.Path(vault)/'.gitignore'
    try:
        if path.is_symlink():raise ValueError('vault .gitignore is a symlink; refusing to edit another target')
        with cp.file_lock(path.with_name('.gitignore.companion.lock')):
            existing=path.read_bytes().decode('utf-8') if path.exists() else ''
            have={line.strip() for line in existing.splitlines()}
            missing=[rule for rule in (*VAULT_IGNORES,'/.gitignore.companion.lock') if rule not in have]
            if not missing:return False
            newline='\r\n' if '\r\n' in existing else '\n'
            block='' if not existing or existing.endswith('\n') else newline
            block+=newline+'# tamanitomo: editor and sync artifacts'+newline+newline.join(missing)+newline
            cp.atomic_write(path,existing+block)
    except (OSError,ValueError) as exc:
        if report is not None:report.append('  ! could not update vault .gitignore: '+str(exc))
        return False
    if report is not None:report.append(f'  vault .gitignore: {len(missing)} rule(s) added ({path})')
    return True
TOOLSET_FLAGS=('--toolsets','--enabled-toolsets')
def cron_toolset_flag(command,home):
    """Probe help without creating a job. Installed Hermes 0.21.1 offers neither flag."""
    env={**os.environ,'HERMES_HOME':home,'PYTHONUTF8':'1'}
    try:
        result=subprocess.run(list(command)+['cron','create','--help'],capture_output=True,
            text=True,encoding='utf-8',timeout=30,env=env)
    except (OSError,subprocess.SubprocessError):return None
    if result.returncode:return None
    flags=set(re.findall(r'--[a-z][a-z-]*',result.stdout))
    return next((f for f in TOOLSET_FLAGS if f in flags),None)
SUPPORTED_FLAG_CACHE={}

def hermes_supports(command,home,flag):
    """Ask this Hermes what it accepts before using a flag on it.

    The kit has to run against whatever version is installed, and a create that
    fails on an unknown flag is a job that silently never exists.
    """
    key=(tuple(command),flag)
    if key in SUPPORTED_FLAG_CACHE:return SUPPORTED_FLAG_CACHE[key]
    try:
        r=subprocess.run(list(command)+['cron','create','--help'],capture_output=True,text=True,
            encoding='utf-8',timeout=60,env={**os.environ,'HERMES_HOME':str(home)})
        ok=r.returncode==0 and flag in (r.stdout or '')
    except (OSError,subprocess.SubprocessError):ok=False
    SUPPORTED_FLAG_CACHE[key]=ok
    return ok

def _create_job_via_hermes(c,name,expr,prompt,toolsets=(),script=None,spec=None,report=None):
    """Create once using only flags advertised by this Hermes CLI.

    Unsupported per-job toolsets use Hermes defaults and are reported explicitly.
    Failures stay pending; retrying a nonzero create could duplicate a committed job.
    """
    if os.environ.get('COMPANION_NO_HERMES_CRON','').lower() in ('1','true','yes'):return False,False
    spec=spec or {};report=report if report is not None else []
    cmd=cp.hermes_command('cron','create',expr,prompt,'--name',name,'--deliver','local')
    base=tuple(cp.hermes_command())
    import yaml
    config=yaml.safe_load((c.home/'config.yaml').read_text(encoding='utf-8')) or {}
    model=config.get('model') or {}
    if script:cmd+=['--script',pathlib.Path(script).name,'--no-agent']
    if not script:
        # A tier the user chose beats the profile default; the profile default
        # beats nothing. The kit never invents a model name.
        pick=c.tier_model(spec.get('tier','')) if spec.get('tier') else {}
        chosen=pick.get('model') or (model.get('default') if isinstance(model,dict) else None)
        provider=pick.get('provider') or (model.get('provider') if isinstance(model,dict) else None)
        if chosen:cmd+=['--model',str(chosen)]
        if provider:cmd+=['--provider',str(provider)]
        if pick.get('base_url'):
            if not hermes_supports(base,c.home,'--base-url'):raise ValueError('Update Hermes to use custom job endpoints')
            cmd+=['--base-url',pick['base_url']]
        effort=pick.get('reasoning_effort')
        if effort and hermes_supports(base,c.home,'--reasoning-effort'):
            cmd+=['--reasoning-effort',str(effort)]
        if spec.get('continuity') and hermes_supports(base,c.home,'--continuity'):
            cmd+=['--continuity']
        if spec.get('preread'):
            path=write_preread_script(c,spec,'preread')
            if hermes_supports(base,c.home,'--script'):cmd+=['--script',path.name]
        if spec.get('monitor'):
            path=write_preread_script(c,spec,'fingerprint')
            if hermes_supports(base,c.home,'--monitor-script'):cmd+=['--monitor-script',path.name]
    if not c.cron_active and not script:cmd+=['--paused','--paused-reason','Paused by tamanitomo setup choice']
    env={**os.environ,'HERMES_HOME':str(c.home),'HERMES_TIMEZONE':c.timezone,'PYTHONUTF8':'1'}
    flag=cron_toolset_flag(tuple(cp.hermes_command()),str(c.home)) if toolsets else None
    if flag:cmd+=[flag,','.join(toolsets)]
    try:
        result=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8',timeout=180,env=env)
    except (OSError,subprocess.SubprocessError):return False,False
    # Never retry a failed create: it might have committed before reporting failure.
    return result.returncode==0,bool(flag)
def seed_open_loops(c,report):
    """One real loop to start with: the SOUL sections the interview left open.

    A companion with no open loops has nothing to pick up, and the ✎ EDIT
    placeholders are genuinely the first unfinished thing between these two.
    """
    import companion_loops as loops
    if loops.loops(c,None):return
    soul=c.soul.read_text(encoding='utf-8') if c.soul.exists() else ''
    if not edit_count(soul):return
    try:
        loops.add(c,{'title':f"Finish {c.agent}'s SOUL.md",
                     'detail':f'{edit_count(soul)} section(s) are still marked ✎ EDIT.',
                     'gentle_use':f'This one is {c.human}\'s to finish. Mention it only if '
                                  f'{c.h_subj()} asks what is left to set up.'},
                  dt.datetime.now(dt.timezone.utc))
        report.append('  open loops: seeded with the unfinished SOUL sections')
    except (OSError,ValueError):pass

def write_preread_script(c,spec,mode):
    """The script Hermes runs before the model, or instead of running it at all.

    `preread` output is injected into the prompt; `fingerprint` output is hashed,
    and an unchanged hash means Hermes skips the run. Same helper, two modes, so
    the two can never describe different sources.
    """
    module=spec.get('monitor_module','companion_preread') if mode=='fingerprint' else 'companion_preread'
    path=c.home/'scripts'/f"companion-{spec['key'].replace('_','-')}-{mode}.py"
    argv=[module+'.py','--home',str(c.home),mode]
    cp.atomic_write(path,'"""Generated by tamanitomo. Prints context; calls no model."""\n'
        'import runpy,sys\n'
        f'sys.path.insert(0,{str(KIT/"kit/scripts")!r})\n'
        f'sys.argv={argv!r}\n'
        f'runpy.run_module({module!r},run_name="__main__")\n')
    return path

def write_job_script(c,spec):
    """A tiny shim Hermes can run with --script --no-agent.

    Hermes takes a script name, not a command line, so each no-agent job gets a
    one-file wrapper that runs the kit helper against this profile. Nothing here
    calls a model.
    """
    detail=spec.get('script') or {}
    module=str(detail.get('module') or '');args=[str(a) for a in (detail.get('args') or [])]
    if not module:return None
    path=c.home/'scripts'/f"companion-{spec['key'].replace('_','-')}.py"
    argv=[module+'.py','--home',str(c.home)]+args
    cp.atomic_write(path,'"""Generated by tamanitomo. Runs one kit helper with no model."""\n'
        'import runpy,sys\n'
        f'sys.path.insert(0,{str(KIT/"kit/scripts")!r})\n'
        f'sys.argv={argv!r}\n'
        f'runpy.run_module({module!r},run_name="__main__")\n')
    return path

def install_jobs(c,m,report):
    write(c.life/'PRESENCE.md',cr.render_template('PRESENCE.md.tmpl',m),overwrite=True)
    with cp.file_lock(c.home/'.companion-jobs.lock'):
        return _install_jobs_locked(c,m,report)
def _install_jobs_locked(c,m,report):
    """Hermes alone owns its scheduler store. Persist failed specs for retry."""
    path=c.home/'cron/jobs.json'
    existing={j.get('name'):j for j in _read_jobs(path).get('jobs',[])}
    if c.image_timeline:(c.data/'image-timeline').mkdir(parents=True,exist_ok=True)
    pending=[];made=0;without_toolsets=[]
    for spec in load_manifest(c)['jobs']:
        name=cr.render(spec['name'],m)
        if name in existing:
            job=existing[name]
            additions=[]
            template=(T/'cron'/spec['file']).read_text(encoding='utf-8')
            # Early structured workers were installed as --no-agent scripts
            # whose argv contained a provider URL/model/API-key name. Editing
            # the cron model pin could never affect them. Migrate only that
            # recognizable kit-owned shape back to a native Hermes agent job;
            # unrelated script jobs remain untouched.
            legacy_script=str(job.get('script') or '')
            if (not spec.get('no_agent') and job.get('no_agent') and
                    legacy_script.startswith('companion-local-')):
                rendered=cr.render(template,m);backups=c.home/'cron/prompt-backups'
                backups.mkdir(parents=True,exist_ok=True)
                stamp=dt.datetime.now().strftime('%Y%m%dT%H%M%S')
                (backups/f'{name}-{stamp}-legacy-worker.md').write_text(job.get('prompt',''),encoding='utf-8')
                updates=['--prompt',rendered,'--agent']
                if spec.get('preread'):
                    updates+=['--script',write_preread_script(c,spec,'preread').name]
                else:updates+=['--script','']
                if spec.get('monitor'):
                    updates+=['--monitor-script',write_preread_script(c,spec,'fingerprint').name]
                else:updates+=['--monitor-script','']
                if spec.get('continuity'):updates+=['--continuity']
                result=subprocess.run(cp.hermes_command('cron','edit',job['id'],*updates),
                    capture_output=True,text=True,encoding='utf-8',timeout=60,
                    env={**os.environ,'HERMES_HOME':str(c.home),'HERMES_TIMEZONE':c.timezone})
                if result.returncode:
                    report.append(f'  ! could not migrate {name} away from its legacy provider-pinned worker')
                else:
                    job={**job,'prompt':rendered,'no_agent':False,
                         'script':write_preread_script(c,spec,'preread').name if spec.get('preread') else None}
                    record_fingerprint(c,name,rendered)
                    report.append(f'  {name}: migrated to native Hermes model routing')
            for marker in ('MEMORY CHECK:','LIVED STATE v1:','PRESENCE CHECK:','DAY CONTINUITY v2:'):
                if marker not in job.get('prompt',''):
                    check=next((line for line in template.splitlines() if line.startswith(marker)),None)
                    if check:additions.append(cr.render(check,m))
            updates=[]
            if additions:
                prompt='\n\n'.join(additions)+'\n\n'+job.get('prompt','')
                updates+=['--prompt',prompt]
            if spec['key']=='pulse' and job.get('schedule',{}).get('expr')=='*/15 6-23 * * *':
                updates+=['--schedule',spec['expr']]
            if updates:
                try:
                    result=subprocess.run(cp.hermes_command('cron','edit',job['id'],*updates),
                        capture_output=True,text=True,timeout=30,
                        env={**os.environ,'HERMES_HOME':str(c.home),'HERMES_TIMEZONE':c.timezone})
                    if result.returncode:raise ValueError('Hermes cron edit failed')
                    report.append(f'  continuity instructions updated for {name}')
                except (OSError,ValueError,subprocess.SubprocessError):
                    report.append(f'  ! could not update {name}; retry repair')
            continue
        prompt=cr.render((T/'cron'/spec['file']).read_text(encoding='utf-8'),m)
        toolsets=[str(t) for t in (spec.get('toolsets') or [])]
        script=write_job_script(c,spec) if spec.get('no_agent') else None
        expr=cr.render(spec['expr'],m)
        created,applied=_create_job_via_hermes(c,name,expr,prompt,toolsets,script=script,
                                               spec=spec,report=report)
        if created:
            made+=1
            record_fingerprint(c,name,prompt)
            if toolsets and not applied:without_toolsets.append(name)
        else:pending.append({'name':name,'expr':expr,'prompt':prompt,'toolsets':toolsets})
    if not c.image_timeline:
        job=existing.get(c.agent+' image timeline')
        if job and job.get('enabled'):
            result=subprocess.run(cp.hermes_command('cron','pause',job['id']),capture_output=True,text=True,timeout=30,
                env={**os.environ,'HERMES_HOME':str(c.home)})
            if result.returncode:report.append('  ! could not pause image timeline; retry repair')
    staging=c.home/'companion-pending-jobs.json'
    if pending:
        cp.atomic_write(staging,json.dumps(pending,ensure_ascii=False,indent=2))
        report.append(f'  ! cron: {len(pending)} pending; Hermes CLI failed or was disabled. Run repair after fixing Hermes.')
    elif staging.exists():staging.unlink()
    report.append(f'  cron jobs: {made} added via `hermes cron create`')
    if without_toolsets:
        report.append(f'  ! this Hermes exposes no supported per-job toolset flag; {len(without_toolsets)} job(s) '
                      f'were created with whatever toolsets it defaults to. Check that they can '
                      f'reach file and terminal, or set them in Hermes.')
    return made
# ---------------------------------------------------------------- prompt fingerprints
# Hermes owns a cron prompt once the job exists, and the user is free to edit it
# there. So the kit records a hash of every prompt it wrote. A prompt that still
# hashes to what we wrote is unedited and safe to re-render when the template
# improves; anything else is someone's work and is never overwritten silently.
FINGERPRINT_FILE='cron/prompt-fingerprints.json'

def _fingerprint(text):
    import hashlib
    # Hermes normalizes CLI prompt arguments with strip(). Treat that boundary
    # whitespace identically; meaningful user changes remain protected.
    return hashlib.sha256((text or '').strip().encode('utf-8')).hexdigest()

def read_fingerprints(c):
    try:return json.loads((c.home/FINGERPRINT_FILE).read_text(encoding='utf-8'))
    except (OSError,ValueError):return {}

def record_fingerprint(c,name,prompt):
    data=read_fingerprints(c);data[name]=_fingerprint(prompt)
    path=c.home/FINGERPRINT_FILE;path.parent.mkdir(parents=True,exist_ok=True)
    cp.atomic_write(path,json.dumps(data,ensure_ascii=False,indent=2,sort_keys=True))

def _edit_prompt(c,job,prompt):
    result=subprocess.run(cp.hermes_command('cron','edit',job['id'],'--prompt',prompt),
        capture_output=True,text=True,encoding='utf-8',timeout=60,
        env={**os.environ,'HERMES_HOME':str(c.home),'HERMES_TIMEZONE':c.timezone})
    if result.returncode:raise ValueError('Hermes cron edit failed')

def refresh_templates(c,m,report,force=False):
    """Bring installed job prompts up to the kit's current templates.

    Without this, a fix to a prompt — the batch-file recording that replaced
    quoted prose, say — only ever reaches new installs, and every existing
    companion keeps running the broken instruction forever.
    """
    jobs={j.get('name'):j for j in _read_jobs(c.home/'cron/jobs.json')['jobs']}
    stored=read_fingerprints(c);backups=c.home/'cron/prompt-backups'
    for spec in load_manifest(c)['jobs']:
        name=cr.render(spec['name'],m);job=jobs.get(name)
        if not job:continue
        current=job.get('prompt','')
        rendered=cr.render((T/'cron'/spec['file']).read_text(encoding='utf-8'),m)
        if current.strip()==rendered.strip():
            if stored.get(name)!=_fingerprint(rendered):record_fingerprint(c,name,rendered)
            continue
        import hashlib
        previous={_fingerprint(current),hashlib.sha256(current.encode('utf-8')).hexdigest(),
                  hashlib.sha256((current+'\n').encode('utf-8')).hexdigest()}
        unedited=bool(stored.get(name)) and stored[name] in previous
        if not (unedited or force):
            why=('it was edited after the kit wrote it' if stored.get(name)
                 else 'this kit never recorded writing it, so it cannot be told from your own edits')
            report.append(f'  ! {name} runs an older prompt and {why}; it was left alone. '
                          f'Re-render it with: companion repair --prompts force '
                          f'(your version is backed up first)')
            continue
        try:
            backups.mkdir(parents=True,exist_ok=True)
            stamp=dt.datetime.now().strftime('%Y%m%dT%H%M%S')
            (backups/f'{name}-{stamp}.md').write_text(current,encoding='utf-8')
            _edit_prompt(c,job,rendered)
            record_fingerprint(c,name,rendered)
            report.append(f'  {name}: prompt re-rendered from the current template'
                          +('' if unedited else f' (previous text saved under {backups})'))
        except (OSError,ValueError,subprocess.SubprocessError):
            report.append(f'  ! could not re-render {name}; it still runs the older prompt')

# Settings that setup renders into installed cron prompts. Hermes owns those
# prompts once created, and the user may have edited them, so a change replaces
# the exact sentence this kit wrote last time rather than re-rendering the job.
PROSE_KEYS=('QUIET','OUTREACH_POLICY')
def prose(m,key):return cr.render(m[key],m)
def refresh_prose(old,new,report):
    """Carry a settings change into the job prompts that quote it.

    The outreach gate itself reads companion.json on every send, so the rule is
    already in force; this is what stops the agent from being told a window its
    own instructions still describe differently."""
    m_old,m_new=mapping(old,{}),mapping(new,{})
    changed=[k for k in PROSE_KEYS if prose(m_old,k)!=prose(m_new,k)]
    if not changed:return
    jobs={j.get('name'):j for j in _read_jobs(new.home/'cron/jobs.json')['jobs']}
    for spec in load_manifest(new)['jobs']:
        job=jobs.get(cr.render(spec['name'],m_new))
        if not job:continue
        template=(T/'cron'/spec['file']).read_text(encoding='utf-8')
        # Only the keys this job's template actually quotes: the pulse never
        # mentions the outreach policy, and must not be reported as missing it.
        keys=[k for k in changed if '{{'+k+'}}' in template]
        if not keys:continue
        prompt=job.get('prompt','');updated=prompt;stale=[]
        for key in keys:
            was,now=prose(m_old,key),prose(m_new,key)
            if was and was in updated:updated=updated.replace(was,now)
            elif now not in updated:stale.append(key)
        if updated!=prompt:
            try:
                result=subprocess.run(cp.hermes_command('cron','edit',job['id'],'--prompt',updated),
                    capture_output=True,text=True,encoding='utf-8',timeout=30,
                    env={**os.environ,'HERMES_HOME':str(new.home),'HERMES_TIMEZONE':new.timezone})
                if result.returncode:raise ValueError('Hermes cron edit failed')
                record_fingerprint(new,job['name'],updated)
                report.append(f"  {job['name']}: updated {', '.join(k.lower() for k in keys)}")
            except (OSError,ValueError,subprocess.SubprocessError):
                report.append(f"  ! could not update {job['name']}; its prompt still states the old value. Retry, or edit the job in Hermes")
        if stale:
            report.append(f"  ! {job['name']} no longer contains the {'/'.join(k.lower() for k in stale)} wording this kit wrote; "
                          f"it was edited by hand, so update it there too")
def refresh_schedules(old,new,report,run_cmd=None):
    """Carry cadence / timing changes into installed cron job schedules.

    If a job's schedule in Hermes matches what the kit previously rendered (was),
    it is updated to the newly computed schedule (now). Custom schedules edited
    by the user in Hermes are left untouched.
    """
    if not (new.home/'cron/jobs.json').exists():return
    m_old,m_new=mapping(old,{}),mapping(new,{})
    specs_old={cr.render(spec['name'],m_old):spec for spec in load_manifest(old)['jobs']}
    specs_new={cr.render(spec['name'],m_new):spec for spec in load_manifest(new)['jobs']}
    with cp.file_lock(new.home/'.companion-jobs.lock'):
        for job in _read_jobs(new.home/'cron/jobs.json').get('jobs',[]):
            spec_old=specs_old.get(job.get('name'))
            spec_new=specs_new.get(job.get('name'))
            if not (spec_old and spec_new):continue
            was=cr.render(spec_old['expr'],m_old)
            now=cr.render(spec_new['expr'],m_new)
            current_expr=job.get('schedule',{}).get('expr')
            if was!=now and current_expr==was:
                try:
                    if run_cmd is not None:
                        result=run_cmd(['cron','edit',job['id'],'--schedule',now],home=new.home)
                    else:
                        result=subprocess.run(
                            cp.hermes_command('cron','edit',job['id'],'--schedule',now),
                            capture_output=True,text=True,encoding='utf-8',timeout=30,
                            env={**os.environ,'HERMES_HOME':str(new.home),'HERMES_TIMEZONE':new.timezone}
                        )
                    if getattr(result,'returncode',0):
                        report.append(f"  ! could not update schedule for {job.get('name',job['id'])}; retry repair")
                    else:
                        report.append(f"  {job.get('name',job['id'])}: schedule updated {was} -> {now}")
                except (OSError,ValueError,subprocess.SubprocessError) as exc:
                    report.append(f"  ! could not update schedule for {job.get('name',job['id'])}: {exc}")

def install_hook(c,m,report):
    guide=c.home/'skills/companion-image-workflows/SKILL.md'
    guide_source=(T/'skills/companion-image-workflows/SKILL.md').read_text(encoding='utf-8')
    if not guide.exists():
        guide.parent.mkdir(parents=True,exist_ok=True)
        cp.atomic_write(guide,cr.render(guide_source,m))
        report.append('  installed structured image workflow guide')
    import yaml
    hook=c.home/'hooks/companion-context.py'
    cfg=c.home/'config.yaml'
    data=yaml.safe_load(cfg.read_text(encoding='utf-8')) or {} if cfg.exists() else {}
    if not isinstance(data,dict):raise ValueError('config.yaml must be a mapping')
    data['timezone']=c.timezone
    hooks=data.get('hooks') or {}
    if not isinstance(hooks,dict):raise ValueError('Invalid Hermes hooks configuration')
    pre=hooks.get('pre_llm_call') or []
    if not isinstance(hooks,dict) or not isinstance(pre,list):raise ValueError('Invalid Hermes hooks configuration')
    cmd=cp.python_command(hook)
    old=c.home/'hooks/inject-continuity.sh'
    # Migrate only the previous kit-owned script. An unrelated continuity hook
    # must be reviewed by its owner instead of silently running two injections.
    legacy=old.exists() and any(k in old.read_text(encoding='utf-8') for k in ('tamanitomo continuity hook','companion-kit continuity hook'))
    cleaned=[]
    for entry in pre:
        value=entry.get('command','') if isinstance(entry,dict) else ''
        if value==cmd:continue
        if 'inject-continuity.sh' in value:
            if legacy and value in (str(old),'~/.hermes/hooks/inject-continuity.sh'):continue
            report.append('  ! unrelated continuity hook already registered; inspect config.yaml before installing this hook')
            return
        cleaned.append(entry)
    source=("# tamanitomo continuity hook; generated for this profile.\n"
            "import json, os, pathlib, runpy, sys\n"
            f"home=pathlib.Path({str(c.home)!r}).resolve()\n"
            "active=pathlib.Path(os.environ.get('HERMES_HOME',str(home))).expanduser().resolve()\n"
            "if active != home:\n    print(json.dumps({'context':''}));sys.exit(0)\n"
            f"sys.path.insert(0,{str(KIT/'kit/scripts')!r})\n"
            "sys.argv=['companion_context.py','--home',str(home)]\n"
            "runpy.run_module('companion_context',run_name='__main__')\n")
    if not hook.exists() or hook.read_text(encoding='utf-8')!=source:cp.atomic_write(hook,source)
    cleaned.append({'command':cmd});hooks['pre_llm_call']=cleaned

    # A second, much smaller hook: when a session ends, write a flag. A cron job
    # gated on that flag reflects within minutes instead of at four in the
    # morning, while the conversation it is reflecting on is still in front of
    # it. This hook writes one file and prints an empty object; it never speaks.
    end_hook=c.home/'hooks/companion-session-end.py'
    end_source=("# tamanitomo session-end flag; generated for this profile.\n"
        "import json, os, pathlib, runpy, sys\n"
        f"home=pathlib.Path({str(c.home)!r}).resolve()\n"
        "active=pathlib.Path(os.environ.get('HERMES_HOME',str(home))).expanduser().resolve()\n"
        "if active != home:\n    print(json.dumps({}));sys.exit(0)\n"
        f"sys.path.insert(0,{str(KIT/'kit/scripts')!r})\n"
        "sys.argv=['companion_checkin.py','--home',str(home),'flag']\n"
        "runpy.run_module('companion_checkin',run_name='__main__')\n")
    if not end_hook.exists() or end_hook.read_text(encoding='utf-8')!=end_source:
        cp.atomic_write(end_hook,end_source)
    end_cmd=cp.python_command(end_hook)
    ends=[e for e in (hooks.get('on_session_end') or [])
          if not (isinstance(e,dict) and e.get('command')==end_cmd)]
    ends.append({'command':end_cmd});hooks['on_session_end']=ends
    data['hooks']=hooks
    if cfg.exists():shutil.copy2(cfg,cfg.with_name('config.yaml.pre-companion-'+uuid.uuid4().hex[:8]))
    cp.atomic_write(cfg,yaml.safe_dump(data,sort_keys=False,allow_unicode=True))
    report.append('  hook: registered portable Python command')
    report.append('  ! approve this hook when Hermes asks on the first interactive chat; unattended runs require that consent')
    report.append("    with nobody at the keyboard: hermes -p <profile> chat -q 'hello' --oneshot --accept-hooks")
def offer_multiplex(c,report,answers=None):
    """Choose one gateway owner and optionally open native Hermes setup."""
    import companion_gateway as cg
    answers=dict(answers or {})
    health=cg.preflight(c)
    report.append('  preflight: '+('existing gateway and Telegram setup detected' if health['ready'] else 'some gateway/Telegram checks need attention'))
    for note in health['notes']:report.append('  ! '+note)
    if 'multiplex' in answers and 'gateway_mode' not in answers:
        answers['gateway_mode']='shared' if wiz.as_bool(answers['multiplex']) else 'later'
    if wiz._tty():
        wiz.banner('Gateway ownership','Each agent keeps its own identity, jobs, memory and bot.')
        print('  Shared: one service runs several profiles. Less maintenance and overhead;')
        print('          one restart affects everyone. Each Telegram agent still needs its own bot.')
        print('  Dedicated: one service per profile. Independent restarts and troubleshooting;')
        print('             more services to maintain. Exclude it from the root multiplexer.')
        print('  Neither option isolates secrets from processes sharing the same OS user.')
    mode=ask('Who should run this agent? Keep current routing preserves an existing working setup.',3,[('shared','Shared root gateway'),
        ('dedicated','Dedicated profile gateway'),('later','Keep current routing; decide later')],answers,'gateway_mode')
    result=cg.configure(c,mode)
    report.append(f'  gateway: {mode}; profile home {c.home}')
    if result['restart_required']:
        report.append('  ! routing changed: restart the existing root gateway before starting a separate profile gateway')
    action=ask('Gateway next step',1,[('later','Finish first; configure gateway later'),
        ('status','Inspect native gateway status'),('setup','Open Hermes bot/platform setup'),
        ('install','Install a dedicated service through Hermes'),('start','Start the dedicated service')],answers,'gateway_action')
    if action!='later':
        code=cg.native(c,action,root_restarted=wiz.as_bool(answers.get('root_restarted',False)))
        if code:report.append(f'  ! gateway {action} returned {code}; run tamanitomo gateway to resolve it')
    report.append('  gateway controls: tamanitomo --home "'+str(c.home)+'" gateway')
# A rendered companion SOUL always carries this line, from the template's header
# comment. It is how both setup and doctor tell "identity written" from "identity
# never rendered", without guessing from prose.
SOUL_MARKER='Generated by tamanitomo'

# `hermes profile create` writes its own default SOUL.md into every new profile.
# It is a stock system prompt, not something a person authored, so setup replaces
# it (after a backup) rather than leaving the companion wearing it. Anything else
# already in the file is treated as the user's writing and left alone.
STOCK_SOUL_OPENINGS=('You are Hermes Agent','You are a helpful AI assistant')

def is_stock_soul(text):
    body=(text or '').strip()
    return bool(body) and body.startswith(STOCK_SOUL_OPENINGS)

def place_soul(c,report,answers=None):
    """Preflight symlink support before moving identity. Never create twin truths."""
    if not c.soul_in_vault:return
    if c.soul_linked:return
    here=c.soul;target=c.canonical_soul
    if here.is_symlink():
        raise ValueError('SOUL.md already links elsewhere; preserve and resolve it before adopting this profile')
    if here.exists() and here.read_text(encoding='utf-8').strip() and c.is_root:
        if not confirm('Move the existing SOUL into the vault (preserving a backup)?',answers,'move_soul',True):
            c.soul_in_vault=False;report.append('  SOUL.md: retained in Hermes home');return
    if target.exists():raise ValueError(f'A canonical SOUL already exists at {target}; resolve the conflict before setup')
    here.parent.mkdir(parents=True,exist_ok=True);target.parent.mkdir(parents=True,exist_ok=True)
    probe=here.with_name('.companion-link-'+uuid.uuid4().hex)
    try:probe.symlink_to(target)
    except OSError:
        c.soul_in_vault=False
        report.append('  SOUL.md: symlinks unavailable; canonical file stays in Hermes home. Back up home AND vault.')
        return
    finally:
        if probe.is_symlink():probe.unlink()
    original=here.read_bytes() if here.exists() else None
    if original is not None:
        backup=c.soul_backups/'SOUL.md.pre-move';backup.parent.mkdir(parents=True,exist_ok=True)
        if backup.exists():backup=backup.with_name(backup.name+'-'+uuid.uuid4().hex[:8])
        backup.write_bytes(original)
    try:
        if original is not None:shutil.move(str(here),str(target))
        else:cp.atomic_write(target,'')
        here.symlink_to(target)
    except OSError:
        if here.is_symlink():here.unlink()
        if not here.exists() and target.exists():shutil.move(str(target),str(here))
        raise
    report.append(f'  SOUL.md: linked to {target}')
def scaffold(c,ans,report,soul_mode='create',raw=None):
    """soul_mode: create (new file) | append (existing agent) | replace."""
    import yaml
    config=c.home/'config.yaml'
    if config.exists():
        parsed=yaml.safe_load(config.read_text(encoding='utf-8')) or {}
        if not isinstance(parsed,dict):raise ValueError('config.yaml must be a mapping')
    m=mapping(c,ans)
    for d in (c.home,c.data,c.life,c.human_dir,c.soul_dir,c.soul_dir/'continuity',
              c.soul_dir/'reflections',c.soul_dir/'ambient',c.home/'hooks',c.home/'cron'):
        d.mkdir(parents=True,exist_ok=True)
    place_soul(c,report,raw)
    soul_text=cr.render_template('SOUL.md.tmpl',m)
    if soul_mode=='keep':
        # Adoption with "keep" means keep. Not "keep unless we recognize it",
        # not "keep the parts we did not write" — the file is left exactly as
        # it is, and the only thing added is the marker for the block the
        # companion writes herself, further down.
        report.append('  SOUL.md: left exactly as it was; only the self-authored block is added')
    elif soul_mode=='create':
        existing=c.soul.read_text(encoding='utf-8') if c.soul.exists() else ''
        blank=not existing.strip()
        stock=is_stock_soul(existing)
        if stock:
            backup=c.soul_backups/'SOUL.md.hermes-default'
            if backup.exists():backup=backup.with_name(backup.name+'-'+uuid.uuid4().hex[:8])
            backup.parent.mkdir(parents=True,exist_ok=True)
            backup.write_text(existing,encoding='utf-8')
        if write(c.soul,soul_text,overwrite=blank or stock):
            report.append('  SOUL.md: written'+(f" (Hermes's default saved to {backup})" if stock else ''))
        else:
            report.append('  ! SOUL.md already had content and was left alone; the companion identity '
                          'was NOT written. Merge it in, or re-run with upgrade --soul append|replace.')
    elif soul_mode=='append':
        prev=c.soul.read_text(encoding='utf-8') if c.soul.exists() else ''
        backup=c.soul_backups/'SOUL.md.pre-companion'
        if backup.exists():backup=backup.with_name(backup.name+'-'+uuid.uuid4().hex[:8])
        backup.parent.mkdir(parents=True,exist_ok=True)
        if prev:backup.write_text(prev, encoding='utf-8')
        banner=('\n\n---\n\n<!-- tamanitomo appended the scaffold below on '
                f'{dt.date.today()}. Your original is unchanged above and backed up at\n'
                f'     {backup}\n'
                '     Merge what you want upward, then delete the rest. Two identities in one\n'
                '     file will read as an inconsistent character. -->\n\n')
        pathlib.Path(c.soul).resolve().write_text(prev.rstrip('\n')+banner+soul_text, encoding='utf-8')
        report.append(f'  SOUL.md: scaffold appended below your original (backup: {backup})')
    else:
        if c.soul.exists():
            backup=c.soul_backups/'SOUL.md.pre-companion'
            if backup.exists():backup=backup.with_name(backup.name+'-'+uuid.uuid4().hex[:8])
            backup.parent.mkdir(parents=True,exist_ok=True);backup.write_text(c.soul.read_text(encoding='utf-8'), encoding='utf-8')
            report.append(f'  SOUL.md: replaced (previous saved to {backup})')
        write(c.soul,soul_text,overwrite=True)
    for tmpl,dest in (('PROTOCOL.md.tmpl',c.life/'PROTOCOL.md'),
                      ('routine.json.tmpl',c.life/'routine.json'),
                      ('PRESENCE.md.tmpl',c.life/'PRESENCE.md'),
                      ('ActiveContext.md.tmpl',c.soul_dir/'ActiveContext.md')):
        write(dest,cr.render_template(tmpl,m))
    try:
        import companion_lifestyle
        seeded=companion_lifestyle.seed(c)
        report.append(f"  wardrobe: {seeded['added_items']} starter pieces; daily care routine enabled")
    except Exception as exc:
        report.append(f"  ! wardrobe seed: {exc}")
    write(c.soul_dir/'Emotive.md',f'# Emotive — {c.agent}\n')
    seed_open_loops(c,report)
    # The heading format is load-bearing: weekly rotation dates an entry by the
    # ISO date in its '## ' heading, and anything undated cannot be filed by month.
    write(c.soul_dir/'Lifelog.md',
          f'# Lifelog — {c.agent}\n\n'
          f'<!-- One entry per day, headed exactly "## YYYY-MM-DD". The weekly hygiene job\n'
          f'     rotates entries older than 180 days into continuity/archive/Lifelog-YYYY-MM.md;\n'
          f'     it reads that date to know what is old, so keep the format. Nothing is deleted. -->\n')
    write(c.soul_dir/'continuity/Autonomy.md',f'# Autonomy log — {c.agent}\n')
    ensure_vault_gitignore(c.vault,report)
    try:
        import companion_vault
        state=companion_vault.init(c)
        if state.get('created'):report.append(f'  vault: now a local git repo at {c.vault}')
        elif not state.get('ready'):report.append(f"  ! vault history unavailable: {state.get('reason')}")
    except (OSError,ValueError,ImportError) as exc:
        report.append(f'  ! could not start the vault history ({exc}); companion restore will not work')
    write(c.human_dir/'README.md',
          f"# {c.human} — what {c.agent} actually knows\n\n"
          f"`facts.jsonl` is append-only and every entry cites evidence. Read it with\n"
          f"`{m['SELF_CMD']} profile`.\n")
    c.save()
    try:
        import companion_integrity
        companion_integrity.sign_creation(c)
    except Exception:pass
    install_hook(c,m,report)
    install_jobs(c,m,report)
    offer_multiplex(c,report,raw)
    # The self-authored block: create it if the SOUL we just wrote lacks one.
    import companion_self as slf
    try:
        if slf.BEGIN not in c.soul.read_text(encoding='utf-8'):
            slf.soul_init(c);report.append('  SOUL self-authored block: created')
    except OSError:pass
    # Memory caps last, because they are sized from the SOUL that was actually
    # rendered rather than from the one we hoped for.
    try:
        import companion_memory
        plan=companion_memory.recommend_caps(c)
        companion_memory.write_caps(c,plan['caps'])
        report.append(f"  memory: room for {plan['caps']['MEMORY.md']:,} and "
                      f"{plan['caps']['USER.md']:,} characters ({plan['reason']})")
    except (OSError,ValueError,ImportError) as exc:
        report.append(f'  ! could not size the memory caps ({exc}); Hermes defaults stand, '
                      f'which is about a page and a half in total')
    # ActiveContext is assembled, not authored. Do it once now so the file the
    # hook reads is the real thing from the first turn rather than the template.
    try:
        import companion_active
        companion_active.write(c)
    except (OSError,ValueError,ImportError) as exc:
        report.append(f'  ! could not assemble ActiveContext.md ({exc}); the template placeholder stands')
    todo=c.home/'COMPANION-TODO.md'
    checklist=cr.render_template('TODO.md.tmpl',m)+'\n## Run these in order\n'
    for i,(text,cmd) in enumerate(next_steps(c),1):
        checklist+=f'\n{i}. {text}\n'+(f'\n   ```sh\n   {cmd}\n   ```\n' if cmd else '')
    write(todo,checklist,overwrite=True)
    report.append(f'  next steps: {todo}')
def finish(c,report,extra_actions=None):
    """Clear the interview off the screen and show what happened, then what is
    still owed. Paths get their own line so they can be copied."""
    wiz.clear()
    wiz.banner('Setup files ready',f'{c.agent} · review status below and run doctor')
    print()
    print('  '+wiz.C.dim('home:')+' '+str(c.home))
    print('  '+wiz.C.dim('data:')+' '+str(c.data))
    print()
    for line in report[1:]:
        line=line.strip()
        if line.startswith('!'):print('  '+wiz.C.yellow(line))
        else:print('  '+wiz.C.dim(line))
    actions=list(extra_actions or [])
    soul=c.soul.read_text(encoding='utf-8') if c.soul.exists() else ''
    edits=edit_count(soul)
    if edits:
        actions.append((f'{edits} section(s) still marked ✎ EDIT — the parts you skipped',c.soul))
    over=len(soul)-c.soul_warn
    if soul and over>0:
        actions.append((f'SOUL.md is {over:,} chars above the kit’s early-warning target; review available headroom before growing it',c.home/'config.yaml'))
    if actions:
        print()
        print('  '+wiz.C.yellow(wiz.C.bold('Still to do')))
        for i,(text,path) in enumerate(actions,1):
            print()
            print('  '+wiz.C.yellow(f'{i}. {text}'))
            if path:print('     '+wiz.C.cyan(str(path)))
    print()
    print(wiz.C.bold('Next steps — run these in order'))
    for i,(text,cmd) in enumerate(next_steps(c),1):
        print(f'\n  {i}. {text}')
        if cmd:print('     '+wiz.C.cyan(cmd))
    print('\n  These instructions are also saved in '+str(c.home/'COMPANION-TODO.md'))
def next_steps(c):
    cli=lambda *args:cp.python_command(KIT/'bin/companion','--home',c.home,*args)
    steps=[('Open this profile in Hermes:',cli('chat')),
           ('Send a short greeting. If Hermes asks about the companion hook, review and approve it. Then exit the chat with /quit.',None),
           ('With nobody at the keyboard, give that consent non-interactively instead:',
            ("hermes chat -q 'hello' --oneshot --accept-hooks" if c.is_root else
             f"hermes -p {c.profile} chat -q 'hello' --oneshot --accept-hooks")),
           ('Restart the gateway to load this profile’s configuration:',cli('gateway','--action','restart')),
           ('Run the installation check. Resolve any ! items before continuing:',cli('doctor'))]
    if not c.cron_active:steps.append(('Enable the scheduled jobs when you are ready:',cli('schedule','active')))
    steps.extend([(f'Check all {len(load_manifest(c)["jobs"])} schedules and their next run times:',cli('schedule','status')),
                  ('After the next due time, check that Hermes recorded a successful run:',cli('schedule','history')),
                  ('Start chatting with your companion:',cli('chat'))])
    if c.image_timeline:steps.append(('Open the local image timeline after the first successful capture:',str(c.data/'image-timeline/index.html')))
    return steps
