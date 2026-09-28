# Tamanitomo portable website

This is the landing page designed for tamanitomo.com, packaged as editable static files.
It includes the existing design, original project logo and screenshot, three installation tabs,
keyboard navigation, and copy buttons. It does not run the Tamanitomo AI companion itself.

No Node.js, npm, React runtime, server application, database, ChatGPT account, API key,
external font, CDN, or build command is needed to host this package. All page assets are included.
The HTML, CSS, and JavaScript in `site/` are the source files you edit and upload.

## Publish on your own host

1. Unzip the package.
2. Upload the **contents of `site/`** to your host's web root (often called `public_html`, `www`, or `htdocs`).
3. Ensure `index.html` is directly in that web root, beside `styles.css`, `script.js`, and `assets/`.
4. Configure `tamanitomo.com` in that host's domain settings and use the DNS records that host supplies.
5. Enable HTTPS using your host's certificate settings.

For a static hosting service, choose `site/` as the publish directory. There is no build step.
For a subdirectory deployment, upload the same files to that subdirectory; asset paths are relative.

The earlier OpenAI A/TXT records are for the ChatGPT-hosted copy. They are not the DNS settings
for another host. If you move the domain, replace the web-routing records with your new host's
instructions. Preserve unrelated mail and other service records. Verify the new host before switching.
Your existing ChatGPT-hosted copy is unaffected by downloading or editing this bundle.

## Preview locally

Open `site/index.html` in your browser. Navigation and platform tabs work directly.
If your browser blocks clipboard access, the Copy button selects the commands for manual copying.
For an optional local web server, run this from the unpacked bundle directory:

```sh
python3 -m http.server 8080 --directory site
```

Then open `http://localhost:8080`. Stop the local server with Ctrl+C.
Python is only for this optional preview; it is not needed on your production host.

## Make edits directly

| File | Edit here |
| --- | --- |
| `site/index.html` | Headline, paragraphs, links, installation commands, page title, and description |
| `site/styles.css` | Colors in `:root`, typography, spacing, and responsive layouts |
| `site/script.js` | Platform switching, keyboard behavior, and copy behavior |
| `site/assets/tamanitomo-logo.png` | Project logo and favicon |
| `site/assets/companion-home.jpg` | Product screenshot |

Use a text editor to make changes, preview, and upload the changed files. No rebuild is necessary.
Installation commands live in each platform panel's `<pre><code>` block. Copy reads the visible
code block, so changing that block also updates what gets copied.
Keep each tab's `aria-controls` matched to its panel's `id`, and keep the corresponding
`aria-labelledby` links intact. Tabs support arrow keys, Home, and End.

To update the separate ChatGPT-hosted version, request the same edits in its Sites editor or chat.
The downloaded files do not automatically synchronize with that hosted version.
This package has not been committed to your public GitHub repository.

## Hosting and duration

You can retain and edit this downloaded package indefinitely. Its files have no expiration mechanism.
Availability, domain registration, traffic allowances, certificates, and charges on another host
are governed by your chosen provider. This page itself makes no model/API requests.

The ChatGPT-hosted version is a separate managed deployment. As checked on 2026-09-23,
OpenAI documentation says Sites is included with eligible ChatGPT plans during public beta,
with plan-specific limits. It persists beyond the chat that created it. The documentation does
not promise permanent free hosting or establish a fixed lifetime for every deployment.

Official references:
- https://learn.chatgpt.com/docs/sites
- https://learn.chatgpt.com/docs/pricing

## Provenance and notices

Exported from the website source revision:
`91fdee7e4be4cdf1af256f11030643f738cb9037`.

The logo and screenshot came from the Tamanitomo repository:
- https://github.com/tamanitomo/tamanitomo/blob/main/kit/app/static/logo.png
- https://github.com/tamanitomo/tamanitomo/blob/main/docs/assets/screenshots/desktop/01-home-elena.jpg

The original project's license is linked from the website footer and included separately
as `TAMANITOMO-PROJECT-LICENSE.txt`. No new license is assigned to your original brand assets.
The inline interface icons derive from Lucide; its license is included in `LUCIDE-LICENSE.txt`.
