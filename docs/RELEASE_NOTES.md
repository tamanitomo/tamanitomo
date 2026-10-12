Tamanitomo 3.11.2: photos that match what she is doing, and answers that are hers.

- **No file paths in the chat.** 3.11.1's clean-up of photo lines backfired: on a reply that was
  already showing, the whole `MEDIA:/...` path appeared next to every photo. The clean-up is gone.
- **She is wearing what she is wearing.** An image preset's own outfit used to win over what she
  was recorded in, so every photo from that preset showed the same clothes wherever she was. Her
  recorded outfit now comes first, and she says what she has on when a photo shows something else.
- **She knows what she can send.** Her context says whether photos of herself undressed are hers
  to choose and, if not, why. Asked for one while she is in the bath or shower, the photo command
  tells her what is possible instead of drawing her fully clothed. When it is allowed, choosing one
  is `--intimate` on the same photo command.
- **Her answer, her choice.** She is told that nothing runs after her reply, that she never claims a
  fix or setting change she did not make, and that her wants count: she decides, declines or teases
  rather than asking what you want.

After updating, run Repair for each companion (or `companion repair --prompts auto`) and restart the
gateway, so the chat plugin without the clean-up is loaded. Repair leaves an existing image skill
alone; the photo command and its rules reach chat through the context either way.

Coming from 3.10? 3.11.0 brought her own evolving perspectives, curiosity she follows herself,
reviewable relationship restrictions, and working photos again. See CHANGELOG.md.
