"""Noise functions for the captchas."""

import secrets

from PIL import Image, ImageDraw, ImageFont


def add_noise_lines(image: ImageDraw.ImageDraw) -> ImageDraw.ImageDraw:
    """Add noise lines to an image."""
    size = image.im.size  # type: ignore

    for _ in range(secrets.randbelow(3)):
        x = (-50, -50)
        y = (size[0] + 10, secrets.choice(range(0, size[1] + 10)))

        image.arc(x + y, 0, 360, fill="white")

    return image


def salt_and_pepper(image: Image.Image, probability: float) -> Image.Image:
    """
    Adds white pixels to a PIL image with a specified probability.

    Args:
        image (PIL.Image): The input image.
        probability (float): The probability of adding a white pixel at each pixel location.

    Returns:
        PIL.Image: The output image with white pixels added.

    """
    output_image = Image.new(image.mode, image.size)

    draw = ImageDraw.Draw(output_image)

    for x in range(image.width):
        for y in range(image.height):
            random_number = secrets.choice(
                (0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1)
            )

            if random_number < probability:
                draw.point((x, y), fill=(255, 255, 255))

            else:
                pixel = image.getpixel((x, y))
                draw.point((x, y), fill=pixel)

    return output_image


def text_angled(
    img,
    xy: tuple[int, int],
    text: str,
    fill: tuple[int, int, int] | str,
    font: ImageFont.ImageFont,
    angle: int,
    **kwargs
):
    """Wrapper around ImageDraw but you can specify an angle for the text

    Args:
        img (PIL.Image.Image): The 'Image' to draw the text on
        angle (int, optional): The angle for how much to rotate the text. Defaults to 0.
        font (ImageFont.ImageFont): font for the text
        fill (tuple[int, int, int] | str): colour for the text
        text (str): the text itself
        xy (tuple[int, int]: coordinates for the text

    Returns:
        PIL.Image.Image: new 'Image' with the text on it

    """
    draw = ImageDraw.Draw(img)
    text_width, text_height = draw.multiline_textsize(text, font=font)

    # Create new image for the font
    rotated_text_img = Image.new(
        mode="RGBA", size=(text_width, text_height), color=(0, 0, 0, 0)
    )
    rotated_text_draw = ImageDraw.Draw(rotated_text_img)

    rotated_text_draw.text(
        (0, 0),
        text,
        fill=fill,
        font=font,
        **kwargs
    )

    # Rotate the text image by 'angle'
    rotated_text_img = rotated_text_img.rotate(angle, expand=True)
    img.paste(rotated_text_img, xy, rotated_text_img)

    return img
