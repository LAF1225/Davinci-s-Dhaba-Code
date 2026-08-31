# How the two ESP boards share one scan id

## The problem

One physical scan produces two things: a photo and a colour reading. They are
taken by two different boards and they travel to the laptop separately, over
Wi-Fi, arriving in whatever order the network feels like.

The laptop has to put them back together. If it ever pairs a photo of one part
of the cloth with a colour reading from a different part, every number after
that looks completely normal and is wrong. Nothing downstream could detect it,
and nobody would find it afterwards.

So there has to be one label that both halves carry, and only one board is
allowed to make it.

## The rule

**The main ESP32 owns the scan id.** It makes one, sends it down to the XIAO,
and puts the same one on its own upload. The XIAO never invents an id; it sends
back exactly the one it was given.

The main ESP32 owns it because it is the board that decides when a scan
happens: it is the one waiting for the MATRIX board to say the robot has
stopped.

## What an id looks like

```
H001_R2_48213
 |    |    |
 |    |    +-- milliseconds since the board started
 |    +------- region id, which scan area of this textile
 +------------ textile id
```

Readable on purpose. When someone is looking at a folder of scans trying to
work out what went wrong, `H001_R2_48213` tells them more than a random string
would. The milliseconds also mean that a rescan of the same area gets a
different id, so the second attempt does not overwrite the first.

## The sequence for one scan area

```
MATRIX          main ESP32                    XIAO                 laptop
  |                  |                          |                    |
  |  <- MOVE_NEXT ---|                          |                    |
  |  --- MOVING ---> |                          |                    |
  |  --- DONE -----> |                          |                    |
  |                  | makes scan_id            |                    |
  |                  |                          |                    |
  |                  |- TAKE_SCAN,<id>,... ---->|                    |
  |                  |                          | takes the photo    |
  |  <- READ_COLOUR -|                          |                    |
  |  -- COLOUR,r,g,b>|                          |                    |
  |                  |                          |-- photo + <id> --->|
  |                  |--- colour + <id> ------------------------->   |
  |                  |                          |                    | joins
  |                  |<- PHOTO_SENT,<id> -------|                    | them
  |                  |                          |                    |
  |                  |--- what happened to <id>? ----------------->  |
  |                  |<-- continue / rescan / complete ------------- |
  |  <- MOVE_NEXT ---|                          |                    |
```

Notice the photo and the colour reading take different routes to the laptop and
never meet before they get there.

## What the laptop does with them

`laptop_connection_code/match_photo_and_sensor_data_using_scan_id.py` holds
whichever half arrives first and waits for the other one. It is deliberately
strict:

- **both halves must carry the same id.** Nothing gets paired by arriving at a
  similar time, ever.
- **either order is fine.** Photo first or sensor reading first, both normal.
- **the same half arriving twice is an error**, not an overwrite.
- **an id that has already been joined and processed is an error.** That is a
  repeated upload, usually a retry after a reply got lost.
- **a half whose partner never arrives times out**, is logged, and the robot is
  asked to rescan that area. It is never paired with something else.

The timeout is `SCAN_JOIN_TIMEOUT_SECONDS` in
`laptop_ai_code/ai_settings_and_thresholds.py`, thirty seconds by default.

## The one thing that is checked but not enforced

Both boards report the region id. They should agree, because the main ESP32
told the XIAO what it was. When they do not, the joined record carries
`region_ids_agree: false` and the pipeline adds
`photo_and_sensor_region_ids_disagree` to the reasons.

It is a warning rather than a rejection, because the scan id matching already
guarantees the two halves belong together. A region id disagreement means one
of the boards has lost track of where it is, which is worth knowing about but
does not make the pair wrong.

## Things that would break this

- letting the XIAO make its own scan id: the two halves would never match
- pairing by arrival time when an id is missing: silently wrong data
- reusing an id for a rescan: the second attempt overwrites the first
- the laptop guessing at a missing half: the reason the timeout exists
