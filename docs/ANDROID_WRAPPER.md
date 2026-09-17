# Android wrapper plan (no APK built)

Use **shiaho777/web-to-app**, Website/URL mode, to open the HTTPS address of the running Tamanitomo host. Do not package a static export: profiles, voice, chat and files depend on the Python/Hermes backend. The Android app is a client; the Windows/Linux host must remain on and reachable. Web updates appear without rebuilding the APK; native permission/icon/package changes require a new APK signed with the same key.

This configuration was checked against upstream source commit `373f032` on 2026-09-11. It is a proposed device-test profile, not a tested APK or an importable upstream configuration file.

| Setting / source field | Recommended value | Reason |
|---|---|---|
| Start URL | Your own authenticated HTTPS host | Never bake a shared bearer token, publisher credential or somebody else's server into the APK |
| Engine / `kernelFlavor` | System default Android WebView | Start with the supported platform engine; keep Android System WebView updated |
| `javaScriptEnabled`, `domStorageEnabled` | On | Needed for the application and saved session/UI state |
| `desktopMode`, custom user agent / kernel disguise | Off / default | Use the responsive mobile layout |
| `browserToolbarEnabled` | Off | Avoid duplicating the app's navigation |
| `fullscreenEnabled` | Off initially | Keep system bars and keyboard behavior predictable; add immersive mode only after phone testing |
| `zoomEnabled` | On | Preserve accessibility |
| `swipeRefreshEnabled`, `autoRefreshEnabled` | Off | Avoid losing a recording, draft or settings form |
| `clearBrowsingDataOnLaunch` | Off | Retain login between launches |
| `enableCookiePersistence` | On | Support the host's login session |
| `acceptThirdPartyCookies` | Off initially | Same-origin app needs none; only change for a demonstrated login requirement |
| `allowFileAccess`, `allowMixedContent` | Off | App is HTTPS, not file:// or insecure HTTP |
| `mixedContentMode` | Never allow (when available) | Keep authenticated traffic on HTTPS |
| `enableCorsBypass`, `enablePrivateNetworkBridge` | Off | The app uses same-origin endpoints; do not silently weaken origin rules |
| `openExternalLinks` | On, with same-origin navigation retained | Open Civitai/docs in the browser; verify the chosen version's domain routing behavior |
| `downloadEnabled` | On / system download location | Save photos and release packages |
| `mediaAutoplayEnabled` | Off initially | Playback has a user-visible Play fallback; only allow audio autoplay for the trusted app origin if desired |
| APK runtime permissions: `microphone` | On | Voice recording requires RECORD_AUDIO and the Android runtime grant |
| Camera, location, contacts, SMS, call logs, broad storage | Off | Not needed for push-to-talk; image upload should use the system picker |
| Orientation | Unlocked | Test portrait, landscape and keyboard resizing |

Preserve same-origin fetches, POST bodies, audio recording/upload and authenticated downloads. Keep the normal auth flow rather than loading a token-bearing URL. If an OAuth provider rejects embedded WebViews, sign in through its supported external-browser flow; do not spoof a user agent to bypass it.

## Phone acceptance checks before building for others

1. Login persists after closing/reopening; logout actually clears access.
2. Navigation and Android Back don't duplicate screens or unexpectedly close a recording.
3. Keyboard does not cover Send, Talk, Stop playback or photo Delete.
4. Talk requests microphone permission, shows Listening, and stops capture on Send, Cancel, backgrounding and navigation.
5. Voice playback works, including the explicit Play fallback; Bluetooth/headphones are device-tested separately.
6. NSFW thumbnails stay blurred when opening details; Delete works without Reveal.
7. Downloads and image/reference uploads use the system picker correctly.
8. Host offline has a readable error. Reconnecting doesn't resend a submitted message.
9. Updating the host changes the wrapper's UI after refresh without reinstalling the APK.

Sources: [upstream project](https://github.com/shiaho777/web-to-app), [WebApp configuration fields](https://github.com/shiaho777/web-to-app/blob/373f032/app/src/main/java/com/webtoapp/data/model/WebApp.kt), [runtime microphone permission handling](https://github.com/shiaho777/web-to-app/blob/373f032/app/src/main/java/com/webtoapp/ui/shell/ShellPermissionDelegate.kt), [browser microphone requirements](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia).
