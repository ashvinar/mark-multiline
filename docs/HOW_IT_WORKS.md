# How it works

## Simple version

A normal button press tells the scanner to capture one horizontal line. Holding the button while jumping to another line does not reliably produce a useful single stitched image.

The patch watches the camera image. When it believes the pen has left a line, it finishes that scan and starts another one while the physical button stays held. Mark receives ordinary scan images, using the same processing and grouping behavior it already had.

Physical release cancels automatic restarts. The pen is restarting a **scan session**, not rebooting the whole device between lines.

## Blur detection

A grayscale pixel is a brightness number from 0 to 255. A clear black letter against white paper has a sudden brightness jump. A blurred edge has a gradual transition.

```text
Sharp: 20, 20, 20, 230, 230
Blur:  20, 60, 100, 145, 190, 230
```

`paper()` in `capture.c` samples the middle third of the frame vertically and most of its width. It compares pixels two columns apart. It measures:

- `contrast`: brightest minus darkest sampled pixel.
- `maxstep`: strongest sampled two-pixel brightness jump.
- `edge`: number of sampled jumps greater than 20 brightness levels.

The exact rules are:

```text
contrast < 12                                → uncertain
edge >= 2 and maxstep >= 2/3 of contrast       → sharp
maxstep <= 1/2 of contrast                    → blurred
otherwise                                    → uncertain
```

After 20 sharp observations arm the detector, six consecutive blurred frames request a line finish. An uncertain frame clears the consecutive-blur count. Plain white space is uncertain, not proof of a lift. Before a lift is confirmed, tentative frames keep reaching the scanner.

This is a heuristic, not a depth measurement or a trained model. A sharp static edge can imitate text; motion blur can imitate lifting.

## Movement and changing detail

Every fourth camera frame also produces a 24 × 27 grayscale thumbnail. `mark_motion()` compares horizontal and vertical brightness gradients in a central region, away from a static camera border. It searches small image shifts and rejects weak or ambiguous matches. Matching gradients makes it less sensitive to overall exposure changes.

The controller learns the scan direction from several confident observations. While readable detail moves in that direction, it updates a per-line detail baseline. Once armed, three thumbnail observations with detail below one third of that baseline can also request a line finish.

The baseline is relearned for each line. No book title, word, recognized text, font name, or page layout is used in these decisions.

## Finishing a line safely

The controller uses these phases:

```text
LINE → FINISHING → WAIT_PAPER → LINE
physical button release → OFF
```

It queues the original complete key-up handler, lets the existing asynchronous completion/copy work run, then invokes the original key-down handler. A key mutex serializes these operations with real button events. A generation number cancels work belonging to an older button hold.

## Startup buffer

After the camera resumes, the controller checks for plausible sharp text and movement before beginning the new line. It can retain up to eight real native camera buffers in order, reserving native headroom. It submits retained frames after the original callback has counted ownership. It never keeps pointers to frames already returned for reuse.

At capacity, it submits the queue rather than overwriting earlier frames. A failed submission returns the buffer through the original release callback and increments an error count. Real release flushes queued frames; an in-flight frame that becomes stale can still be cancelled.

The buffer protects **new-line startup after camera acquisition resumes**. It does not capture through the factory completion pause, previously measured at approximately 250 ms.

## Potential improvements, not implemented here

Measure sharpness across several regions instead of trusting the strongest edge; learn a more adaptive focus baseline; combine movement and focus evidence over elapsed time; and investigate continuous acquisition through the native completion interval. Each needs independent failed/successful recordings and physical validation. The checked-in controller remains the exact installed version.
