Tamanitomo 3.0.13 is about the relationship itself, and one delivery bug.

- **Messages a companion addressed to you by name now arrive.** A companion could queue a message with your name where the delivery channel belongs, and it failed at send time. The outbox now refuses that when the message is written, holds back any already waiting without using up a day's allowance, and keeps the channel's own reason when a send does fail.
- **Level changes are announced.** The first time you open the app after your relationship reaches a new level, you are told with a pop-up. A drop gets one too. Coming back to a level you have reached before gets a smaller note.
- **Bonded has room to breathe.** Closeness keeps building past the point where Bonded begins, so a quiet week no longer knocks a Bonded relationship straight back down. The meter still reads up to 100%.
- **Some choices wait for Bonded.** The more personal picture settings only appear, and can only be switched on, once a relationship has reached Bonded.

### Install

Download **tamanitomo-release.zip** below, extract it into its own application folder, and run the Tamanitomo launcher. Keep your Hermes home and vault outside that folder. The automatically generated GitHub source archives are for development; use the attached release ZIP for in-app updates.
