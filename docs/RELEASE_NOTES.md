Tamanitomo 3.10.1: album picks follow the Music switch.

- **Spotify only with Music on.** With Music switched off under Settings → Sensors, she does not
  read your Spotify at all: no listening history, no artist or album lookups, and no album picks
  saved or sent. The album instructions and her saved picks also leave her chat and background
  routines. A connected Spotify account on its own is not permission. Picks she already saved
  stay on Us → Albums for you, with a note that Music is off.
- **Top artists need one extra permission.** To let her see your top artists, sign in to Spotify
  again with `user-top-read` added to the requested scopes. Without it she uses what you played
  recently.

After updating, run Repair for each companion (or `companion repair --prompts auto`): it takes
the album instructions out of her autonomy routine, which now gets them only while Music is on.

Coming from 3.9? 3.10.0 brought time together on the Us page, album picks, a Play button on
messages, and the Distant stage. See CHANGELOG.md.
