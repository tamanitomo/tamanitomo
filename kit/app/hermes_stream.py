"""Optional streaming bridge, executed ONLY by Hermes's own Python interpreter.

Keep Hermes's quiet CLI lifecycle, routing, hooks, session persistence and approvals.
If the callback seam changes, retain ordinary final-response behavior.
"""
import contextlib
import io
import json
import sys


def main():
    wire=sys.stdout
    def emit(kind, **values):
        wire.write(json.dumps({'event':kind,**values},ensure_ascii=False)+'\n');wire.flush()
    output=io.StringIO()
    code=0
    with contextlib.redirect_stdout(output):
        import cli
        # These wrap functions belonging to somebody else's program, which is
        # free to grow an argument without telling us. Both forward whatever
        # they are given rather than restating a signature: Hermes 0.21.3 added
        # an `emitter` to the quiet runner and passed it on every call, and a
        # wrapper that named exactly two parameters turned every chat turn into
        # a TypeError while cron, which does not come through here, carried on
        # working. Reported by erohtar (#1), who also found the cause.
        configure=getattr(cli,'_configure_quiet_agent',None)
        if configure:
            def configured(agent,*args,**kwargs):
                configure(agent,*args,**kwargs)
                agent.stream_delta_callback=lambda delta:emit('delta',text=delta) if isinstance(delta,str) else None
            cli._configure_quiet_agent=configured
        quiet=getattr(cli,'_run_quiet_single_query',None)
        if quiet:
            def run(instance,query,*args,**kwargs):
                try:return quiet(instance,query,*args,**kwargs)
                finally:emit('session',id=instance.session_id)
            cli._run_quiet_single_query=run
        from hermes_cli.main import main as hermes_main
        try:hermes_main()
        except SystemExit as exc:code=exc.code or 0
    # Only the reply: a model that thinks out loud in <think> tags keeps its thinking.
    import re
    final=re.sub(r'<(think|thinking|reasoning)>[\s\S]*?(</\1>|$)','',output.getvalue(),flags=re.I)
    emit('final',text=final[-1000000:])
    return code

if __name__=='__main__':sys.exit(main())
