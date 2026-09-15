# Hosted Companion Kit

## Example deployment architecture

- Public URL: https://companion.example.com
- ProxyHost: Traefik → Authelia admin policy → `companion-web` Nginx container on private network.
- BackendHost: `companion-workspace.service` (systemd user service), one backend listening on localhost and private network (e.g. `10.0.0.2:8770` or Tailscale).
- Nginx serves static UI files from `/opt/companion-kit/static` and proxies API/media to the backend over the private network.
- Hermes profiles, vault, model credentials, and jobs remain on the backend host.

The backend token is injected server-side from the root-only Nginx configuration. It is not embedded in public frontend files. Nginx independently checks Authelia on every request, including assets and media. Traefik clears client-supplied identity/token headers before authentication. A host-specific Authelia deny rule prevents non-admins falling through to an API bypass.

This is a single-owner administration workspace. An allowed admin can manage every profile in this backend; it is not tenant isolation for multiple untrusted users. Give each user their own backend and host/authorization policy.

## Start and maintain

On the backend host:

```sh
systemctl --user status companion-workspace
systemctl --user restart companion-workspace
journalctl --user -u companion-workspace --since today
```

The user already has linger enabled, so the service starts without a desktop login. The service file is in `~/.config/systemd/user/companion-workspace.service`; the repository copy in `deploy/` records example paths and addresses. Do not start a second backend against the same profiles. The ordinary launcher reuses this backend.

On the proxy host:

```sh
docker ps --filter name=companion-web
docker logs --tail 50 companion-web
docker restart companion-web
```

The container has `unless-stopped` restart policy, no published host port, a read-only root, and writable temporary mounts. Both machines and private networking must remain available for remote access. Hermes's gateway continues independently when the web backend stops. Browser closure has no effect on either service.

## Updating

Update the kit source/dependencies on the backend host, run its tests, and restart the backend after in-flight app actions complete. Copy matching `kit/app/static/` assets to the proxy host's static directory. Nginx uses no-store responses. The API location also forwards HTTP/1.1 Upgrade/Connection headers for the embedded Hermes dashboard’s WebSockets. Its server-injected backend token authenticates that connection; browser cookies remain stripped at this boundary. Do not copy the access token into that directory or into a shared source ZIP.

Changing/rotating the backend token also requires rendering `deploy/nginx.conf.template` into the proxy host's private Nginx config and reloading Nginx. `COMPANION_PUBLIC_ORIGIN` permits same-origin browser writes through HTTPS termination; it does not replace token authentication. `COMPANION_BIND` is an explicit comma-separated IPv4 listen list. Keep the backend off public interfaces.

Nginx resolves Authelia through Docker DNS (`127.0.0.11`) with a 10-second cache. Keep the variable-based authentication upstream in the template: a literal hostname in `proxy_pass` retains the startup address and can cause HTTP 500 errors after Authelia is recreated.

The Nginx template and user-service example are templates; change addresses, domain, paths, and Authelia upstream for your installation. The template's `BACKEND_TOKEN` placeholder must be rendered privately before use. See [Authelia proxy integration](https://www.authelia.com/integration/proxies/nginx/).

## Rollback

Keep pre-change configuration backups before modifying production proxy policies. Stopping the Companion Kit user service or web container does not stop Hermes's gateway.

## Verification and remaining limits

The public homepage, API, and media redirect to Authelia when signed out, including with forged identity headers. Policy checks deny non-admins. Authenticated browser checks loaded the live companion, protected images, activity feed, and a completed run-history action through the proxy.

The native streaming bridge was exercised with installed Hermes 0.21.1 against a local mock model endpoint, producing real delta callbacks and a session ID. The bridge runs in Hermes's interpreter and retains its quiet CLI lifecycle. The browser receives snapshots at 350 ms intervals, not artificial typing. Providers with streaming disabled may return only a completed response. Streaming relies on Hermes's optional callback seam; retest it after Hermes updates. No Hermes source files are modified.

Chat embeds referenced image/audio/video files only when they resolve through the existing profile-owned content catalog. Remote tracking URLs, files outside that vault, and hidden/credential files are not embedded. The activity feed combines latest job results, next scheduled runs, errors, and saved creations; it is not a complete historical event ledger. Native run history remains available separately.
