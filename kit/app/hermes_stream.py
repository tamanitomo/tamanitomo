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
        configure=getattr(cli,'_configure_quiet_agent',None)
        if configure:
            def configured(agent):
                configure(agent)
                agent.stream_delta_callback=lambda delta:emit('delta',text=delta) if isinstance(delta,str) else None
            cli._configure_quiet_agent=configured
        quiet=getattr(cli,'_run_quiet_single_query',None)
        if quiet:
            def run(instance,query):
                try:return quiet(instance,query)
                finally:emit('session',id=instance.session_id)
            cli._run_quiet_single_query=run
        from hermes_cli.main import main as hermes_main
        try:hermes_main()
        except SystemExit as exc:code=exc.code or 0
    emit('final',text=output.getvalue()[-1000000:])
    return code

if __name__=='__main__':sys.exit(main())
