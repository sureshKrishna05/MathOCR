"""Detection-box geometry for MathOCR.

Authored by Bouronikos Christos <chrisbouronikos@gmail.com>.
Donations are welcome at https://paypal.me/christosbouronikos.

Math formula detectors regularly report one large construction — a tall
fraction, a matrix, an equation with wide superstructure — as several partial
boxes. Recognizing those fragments separately is what used to split equations
into pieces. The functions here merge fragments back into whole regions and
decide when an image should simply be treated as one single formula.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Box:
    """An axis-aligned rectangle in image pixel coordinates."""

    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return max(0.0, self.right - self.left)

    @property
    def height(self) -> float:
        return max(0.0, self.bottom - self.top)

    @property
    def area(self) -> float:
        return self.width * self.height

    def union(self, other: Box) -> Box:
        return Box(
            min(self.left, other.left),
            min(self.top, other.top),
            max(self.right, other.right),
            max(self.bottom, other.bottom),
        )

    def expanded(self, dx: float, dy: float) -> Box:
        return Box(self.left - dx, self.top - dy, self.right + dx, self.bottom + dy)

    def clamped(self, width: float, height: float) -> Box:
        return Box(
            min(max(self.left, 0.0), width),
            min(max(self.top, 0.0), height),
            min(max(self.right, 0.0), width),
            min(max(self.bottom, 0.0), height),
        )

    def overlaps(self, other: Box) -> bool:
        return (
            self.left < other.right
            and other.left < self.right
            and self.top < other.bottom
            and other.top < self.bottom
        )


def _horizontal_overlap(a: Box, b: Box) -> float:
    return max(0.0, min(a.right, b.right) - max(a.left, b.left))


def _vertical_overlap(a: Box, b: Box) -> float:
    return max(0.0, min(a.bottom, b.bottom) - max(a.top, b.top))


def _has_reading_order_separator(a: Box, b: Box, separators: list[Box] | None) -> bool:
    """Return whether nearby ordinary text proves stacked boxes are separate.

    A word such as ``or`` placed to the left of the second display equation is
    strong reading-order evidence that the two visually close boxes should not
    be joined as a fraction.  Text inside either box is deliberately ignored:
    it is often the page OCR's imperfect reading of the formula itself.
    """

    if not separators:
        return False
    center_a = (a.top + a.bottom) / 2
    center_b = (b.top + b.bottom) / 2
    lo, hi = sorted((center_a, center_b))
    left = min(a.left, b.left)
    right = max(a.right, b.right)
    height = min(a.height, b.height) or 1.0
    for separator in separators:
        center = (separator.top + separator.bottom) / 2
        if not (lo <= center <= hi):
            continue
        # The separator must sit alongside, rather than within, the proposed
        # formula union.  A generous vertical tolerance accommodates italics.
        if separator.right <= left - 0.08 * height or separator.left >= right + 0.08 * height:
            return True
    return False


def _belong_together(a: Box, b: Box, separators: list[Box] | None = None) -> bool:
    """Decide whether two detected fragments are parts of one formula.

    Three situations are merged:

    1. Rectangles that already overlap — always the same formula.
    2. Side-by-side fragments on the same visual line (an equation cut at an
       operator): strong vertical overlap and a horizontal gap comparable to
       the glyph height.
    3. Stacked fragments (a fraction cut into numerator and denominator):
       strong horizontal overlap and a small vertical gap. The vertical gap
       limit is deliberately tight so consecutive but distinct display
       equations on a page are not glued together.
    """

    if a.overlaps(b):
        return True

    reference = min(a.height, b.height) or 1.0

    vertical_overlap = _vertical_overlap(a, b)
    if vertical_overlap >= 0.5 * reference:
        horizontal_gap = max(a.left, b.left) - min(a.right, b.right)
        if 0 <= horizontal_gap <= 1.2 * reference:
            return True

    narrow = min(a.width, b.width) or 1.0
    horizontal_overlap = _horizontal_overlap(a, b)
    if horizontal_overlap >= 0.6 * narrow:
        vertical_gap = max(a.top, b.top) - min(a.bottom, b.bottom)
        center_offset = abs((a.left + a.right) / 2 - (b.left + b.right) / 2)
        if (
            0 <= vertical_gap <= 0.5 * reference
            and center_offset <= 0.18 * narrow
            and not _has_reading_order_separator(a, b, separators)
        ):
            return True

    return False


def merge_fragmented_boxes(
    boxes: list[Box], *, separators: list[Box] | None = None
) -> list[Box]:
    """Union every group of fragments that belongs to one formula.

    Runs to a fixed point so chains merge fully: numerator↔bar↔denominator
    collapse into one region even when only neighbouring pairs touch.
    """

    merged = list(boxes)
    changed = True
    while changed:
        changed = False
        result: list[Box] = []
        for box in merged:
            for index, existing in enumerate(result):
                if _belong_together(existing, box, separators):
                    result[index] = existing.union(box)
                    changed = True
                    break
            else:
                result.append(box)
        merged = result
    return sorted(merged, key=lambda box: (box.top, box.left))


def padded_crop_box(box: Box, image_width: float, image_height: float) -> Box:
    """Give a region breathing room; recognizers read margins better than cuts."""

    pad = max(4.0, 0.08 * box.height)
    return box.expanded(pad, pad).clamped(image_width, image_height)


# Any image at most this many pixels is assumed to be a cropped formula or a
# small excerpt when detection finds nothing. Screenshots and crops of single
# equations stay well below it; scanned pages and phone photos exceed it.
SMALL_IMAGE_AREA = 1_200_000


def plan_regions(
    image_width: float,
    image_height: float,
    boxes: list[Box],
    *,
    assume_small_is_formula: bool = True,
    separators: list[Box] | None = None,
) -> list[Box] | None:
    """Choose between whole-image recognition and per-region recognition.

    Returns ``None`` when the whole image should be recognized as one formula,
    otherwise the list of merged regions (possibly empty when the page really
    contains no mathematics).
    """

    image_area = max(1.0, image_width * image_height)
    merged = merge_fragmented_boxes(boxes, separators=separators)

    if not merged:
        small = image_area <= SMALL_IMAGE_AREA
        return None if (assume_small_is_formula and small) else []

    dominant = max(merged, key=lambda box: box.area)
    if dominant.area / image_area >= 0.55:
        return None
    if dominant.width / image_width >= 0.8 and dominant.area / image_area >= 0.4:
        return None
    if len(merged) == 1 and image_area <= SMALL_IMAGE_AREA and dominant.area / image_area >= 0.3:
        # A cropped formula with generous margins: recognize the whole image so
        # nothing outside an imperfect detection box is lost.
        return None

    return merged
