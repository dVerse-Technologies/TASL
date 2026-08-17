# Breaking-news video clips

Drop `.mp4` files here and name them in `config/market.json`:

```json
{ "event_id": "WAR", "video": "war.mp4", ... }
```

The stage projector then plays that clip full-screen on a loop instead of the
built-in news slate. The event's ticker line stays along the bottom; everything
else in the clip is yours.

**A missing file cannot black out the projector.** The server checks this
directory when the event fires; if the named file is not here it logs a line to
the console and sends `null`, and the stage falls back to the built-in animated
slate. So a typo costs you the clip, never the flash.

## What works

- **Container/codec:** `.mp4`, H.264 video, AAC audio. That is what Chrome and
  Edge play without arguing.
- **Resolution:** match the projector, usually 1920×1080. The clip is drawn
  with `object-fit: cover`, so a different aspect ratio is cropped, not
  letterboxed.
- **Length:** a few seconds is right. It loops for the event's
  `flash_seconds` (45 by default), so a 5 s sting plays nine times.

## Sound

The stage page shows a **CLICK TO ARM** prompt when it loads. Click it once
during setup. Browsers refuse to autoplay audio on a page nobody has
interacted with, and without that click every clip plays silently.

If it somehow was not armed, the clip still plays — muted. It never blocks.
