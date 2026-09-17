"""The settings screen and the non-interactive --set path behind it."""
from __future__ import annotations
import argparse
import companion_config as cc
import companion_render as cr
import json
import sys
import companion_wizard as wiz
from .common import input, mapping, print, resolve
from .ops import cmd_schedule
from .questions import ask, ask_outreach_cap, check_timezone, parse_cap, pick_key, pick_timezone, strict_hhmm
from .scaffold import install_hook, refresh_prose
from .timeline import cmd_timeline

OUTREACH_LABELS={'free':'yes, socially whenever they want',
                 'updates_only':'only with something real to report',
                 'never':'no, replies only'}
# Everything here is "how it behaves toward you". Identity — persona, boundary,
# names, SOUL prose — is deliberately absent: that is the user's file to edit,
# and a menu that rewrote it would overwrite whatever they had written there.
SETTINGS_KEYS={'quiet_start','quiet_end','outreach','outreach_per_day','timezone','image_style'}
def apply_settings(c,changes):
    """Validate every change, then return the updated companion. Nothing is saved
    here: a bad value in a batch must not leave half of it applied."""
    values=dict(changes)
    for key in ('quiet_start','quiet_end'):
        if key in values:values[key]=strict_hhmm(values[key])
    if 'timezone' in values:values['timezone']=check_timezone(str(values['timezone']).strip())
    if 'outreach' in values:
        if values['outreach'] not in OUTREACH_LABELS:
            raise ValueError('outreach must be one of: '+', '.join(sorted(OUTREACH_LABELS)))
    if 'outreach_per_day' in values:values['outreach_per_day']=parse_cap(values['outreach_per_day'])
    if 'image_style' in values:
        styles=cr.load_styles()
        if values['image_style'] not in styles:
            raise ValueError('unknown image style; run `tamanitomo catalog --category images` to see them')
    updated=cc.dataclasses.replace(c,**values)
    # Replies-only and a daily allowance contradict each other; the gate reads
    # policy first, so leaving a stale cap behind would only mislead the reader.
    if updated.outreach=='never' and 'outreach' in values and 'outreach_per_day' not in values:
        updated=cc.dataclasses.replace(updated,outreach_per_day=0)
    return updated
def commit_settings(c,updated,report):
    """Save, then carry the change into everything that quoted the old value."""
    if updated.to_dict()==c.to_dict():
        report.append('  nothing changed');return c
    updated.save()
    refresh_prose(c,updated,report)
    if updated.timezone!=c.timezone:
        install_hook(updated,mapping(updated,{}),report)
        report.append(f'  timezone {c.timezone} -> {updated.timezone}; Hermes config.yaml updated')
    if updated.image_style!=c.image_style:
        style=cr.load_styles()[updated.image_style]
        report.append(f"  image style -> {style['label']}")
        report.append('  ! SOUL.md still describes the previous style. It is your file, so this does not '
                      'rewrite it; edit its Visual Presence section to:')
        report.append('    '+cr.render(style['soul'],mapping(updated,{})))
    if (updated.quiet_start,updated.quiet_end)!=(c.quiet_start,c.quiet_end):
        report.append(f'  quiet hours {c.quiet_start}-{c.quiet_end} -> {updated.quiet_start}-{updated.quiet_end}, '
                      f'in force from the next outreach attempt')
    if (updated.outreach,updated.outreach_per_day)!=(c.outreach,c.outreach_per_day):
        # "no limit" would read as permission on a companion that never writes first.
        cap='' if updated.outreach=='never' else (
            ' (no daily limit)' if not updated.outreach_per_day else f' (at most {updated.outreach_per_day} a day)')
        report.append(f'  messages first: {OUTREACH_LABELS[updated.outreach]}{cap}')
    return updated
def settings_rows(c):
    """(key, setting, current value). Back has no value and gets no column."""
    styles=cr.load_styles()
    cap='no limit' if not c.outreach_per_day else f'{c.outreach_per_day} a day'
    rows=[('quiet','Change quiet hours',f'{c.quiet_start} to {c.quiet_end}'),
          ('outreach','May they message you first',OUTREACH_LABELS.get(c.outreach,c.outreach))]
    if c.outreach!='never':rows.append(('cap','How often they may message first',cap))
    rows+=[('timezone','Timezone',c.timezone),
           ('style','Image style',styles.get(c.image_style,{}).get('label',c.image_style)),
           ('timeline','Image timeline','on' if c.image_timeline else 'off'),
           ('schedule','Scheduled jobs','active' if c.cron_active else 'paused'),
           ('back','Back','')]
    return rows
def settings_table(rows):
    """Pad the setting names to one width so the values line up under a header.
    Both renderers prefix every row with the same number of characters, so
    padding here is all the alignment there is to do."""
    width=max(len(name) for _,name,_ in rows)
    options=[(f'{name:<{width}} | {value}' if value else name,key) for key,name,value in rows]
    lead=wiz.header_indent()
    header=(lead+f'{"Setting":<{width}} | Currently\n'+
            lead+'-'*width+'-+-'+'-'*max(9,max(len(value) for _,_,value in rows)))
    return options,header
def settings_screen(c):
    """One companion's behaviour settings, edited one at a time so each change
    reports what it touched before the next is chosen."""
    while True:
        wiz.rule(f'{c.agent.upper()} — SETTINGS')
        print(wiz.C.dim(f'  {c.home}'))
        print()
        options,header=settings_table(settings_rows(c))
        action=wiz.choose('What would you like to change?',options,
                          allow_write=False,allow_skip=False,note=header)
        if action=='back':return 0
        report=[]
        try:
            if action=='timeline':
                state=wiz.choose('Image timeline',[('Show status and gallery location','status'),
                    ('Enable one local image every 15 minutes','on'),
                    ('Stop new images; keep 30-day cleanup','off'),('Back','back')],
                    allow_write=False,allow_skip=False,
                    note='Uses the configured Hermes image provider: up to 96 requests/day. Images stay '
                         'local and are never messaged to you. Save favorites outside the folder to keep them.')
                if state!='back':cmd_timeline(argparse.Namespace(home=c.home,state=state))
                c=cc.load(c.home)
            elif action=='schedule':
                state=wiz.choose('Scheduled jobs',[('Authorize and run them','active'),
                    ('Pause them','paused'),('Back','back')],allow_write=False,allow_skip=False)
                if state!='back':cmd_schedule(argparse.Namespace(home=c.home,state=state))
                c=cc.load(c.home)
            else:
                changes={}
                if action=='quiet':
                    changes['quiet_start']=strict_hhmm(ask('Start of your do-not-disturb hours (HH:MM)',c.quiet_start))
                    changes['quiet_end']=strict_hhmm(ask('End of your do-not-disturb hours (HH:MM)',c.quiet_end))
                elif action=='outreach':
                    changes['outreach']=ask('May they message you first?',2,
                        [('free','Yes — socially, whenever they want to'),
                         ('updates_only','Only with something real to report or ask'),
                         ('never','No, replies only')])
                elif action=='cap':
                    changes['outreach_per_day']=ask_outreach_cap()
                elif action=='timezone':
                    changes['timezone']=pick_timezone(c.timezone)
                elif action=='style':
                    changes['image_style']=pick_key('Image style',
                        [(k,v['label']+' — '+v['blurb']) for k,v in cr.load_styles().items()])
                c=commit_settings(c,apply_settings(c,changes),report)
        except (ValueError,OSError) as e:
            report.append('  ! '+str(e))
        except SystemExit as e:
            if e.code:report.append(f'  ! {e}')
        for line in report:
            print(('  '+wiz.C.yellow(line.strip())) if line.strip().startswith('!') else wiz.C.dim(line))
        input('\n  '+wiz.C.dim('press Enter to return to settings'))
        wiz.clear()
def cmd_settings(args):
    """Change quiet hours, message frequency, timezone and images after setup."""
    c=resolve(args,require_config=True)
    pairs=[item.split('=',1) for item in (args.set or [])]
    if any(len(pair)!=2 for pair in pairs):raise ValueError('--set takes key=value')
    changes={k.strip():v for k,v in pairs}
    unknown=sorted(set(changes)-SETTINGS_KEYS)
    if unknown:
        raise ValueError('Unknown setting(s): '+', '.join(unknown)+
                         '\nSettable here: '+', '.join(sorted(SETTINGS_KEYS))+
                         '\nImage timeline and job scheduling have their own commands: timeline, schedule')
    if changes:
        report=['Settings']
        commit_settings(c,apply_settings(c,changes),report)
        for line in report[1:]:print(line)
        return 0
    if not sys.stdin.isatty():
        print(json.dumps({'agent':c.agent,'home':str(c.home),
            'quiet_hours':f'{c.quiet_start}-{c.quiet_end}','timezone':c.timezone,
            'outreach':c.outreach,'outreach_per_day':c.outreach_per_day or None,
            'image_style':c.image_style,'image_timeline':c.image_timeline,
            'cron_active':c.cron_active},indent=2))
        return 0
    return settings_screen(c)
