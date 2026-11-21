"""
The blurred photo shown on match cards. Made on request from the member's own photo;
the real photo never leaves the server through this path.
"""
from io import BytesIO

from PIL import Image, ImageFilter, ImageOps

from domain.matchmaking.models import ProfilePhoto

SIZE = 480          # small: it's a hint of the person, not a portrait
BLUR_RADIUS = 18    # strong enough that the face can't be recognised

# The close-up gives the best overall impression once blurred
PREFERENCE = [ProfilePhoto.Kind.CLOSE_UP, ProfilePhoto.Kind.FULL_LENGTH, ProfilePhoto.Kind.OTHER]


def blurred_jpeg(client):
    """JPEG bytes of the member's photo, heavily blurred, or None if they have no photo."""
    profile = getattr(client, "profile", None)
    if not profile:
        return None
    photos = {p.kind: p for p in profile.photos.all()}
    photo = next((photos[k] for k in PREFERENCE if k in photos), None)
    if not photo:
        return None
    try:
        with photo.image.open("rb") as f, Image.open(f) as original:
            image = ImageOps.exif_transpose(original).convert("RGB")
            image.thumbnail((SIZE, SIZE))
            image = image.filter(ImageFilter.GaussianBlur(BLUR_RADIUS))
            out = BytesIO()
            image.save(out, "JPEG", quality=70)
            return out.getvalue()
    except FileNotFoundError:
        return None