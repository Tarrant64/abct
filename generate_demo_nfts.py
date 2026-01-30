#!/usr/bin/env python3
"""
Generate demo NFT placeholder images for ABCT demo mode
Creates 55 colorful placeholder images with collection names and numbers
"""

from PIL import Image, ImageDraw, ImageFont
import os

# Output directory
output_dir = "frontend/static/demo-nfts"
os.makedirs(output_dir, exist_ok=True)

# Image settings
IMG_SIZE = 400
FONT_SIZE = 24

# Collection configs: (prefix, count, base_color)
collections = [
    ("clay-nation", 15, (100, 180, 255)),     # Light blue
    ("ape-society", 8, (255, 180, 100)),      # Orange
    ("bayc", 12, (180, 100, 255)),            # Purple
    ("smb", 20, (255, 100, 150)),             # Pink
]

def create_nft_image(filename, collection_name, number, base_color):
    """Create a single NFT placeholder image."""
    # Create image with gradient-like effect
    img = Image.new('RGB', (IMG_SIZE, IMG_SIZE))
    draw = ImageDraw.Draw(img)

    # Create gradient background
    for y in range(IMG_SIZE):
        # Darken as we go down
        factor = 1 - (y / IMG_SIZE) * 0.3
        color = tuple(int(c * factor) for c in base_color)
        draw.line([(0, y), (IMG_SIZE, y)], fill=color)

    # Add some geometric shapes for variety
    shape_offset = (number * 17) % 100
    shape_color = tuple(min(255, c + 40) for c in base_color)

    # Draw circles
    circle_x = (shape_offset * 3) % (IMG_SIZE - 80) + 40
    circle_y = (shape_offset * 2) % (IMG_SIZE - 80) + 40
    draw.ellipse([circle_x, circle_y, circle_x + 80, circle_y + 80],
                 fill=shape_color, outline=None)

    # Draw rectangles
    rect_x = ((shape_offset + 50) * 2) % (IMG_SIZE - 100) + 50
    rect_y = ((shape_offset + 30) * 3) % (IMG_SIZE - 60) + 30
    draw.rectangle([rect_x, rect_y, rect_x + 60, rect_y + 60],
                   fill=tuple(max(0, c - 40) for c in base_color))

    # Add text overlay
    try:
        # Try to use a nice font
        font_large = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 32)
        font_small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20)
    except:
        # Fallback to default font
        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # Draw collection name
    collection_display = collection_name.replace('-', ' ').title()
    text_bbox = draw.textbbox((0, 0), collection_display, font=font_large)
    text_width = text_bbox[2] - text_bbox[0]
    text_x = (IMG_SIZE - text_width) // 2

    # Draw text with shadow
    shadow_offset = 2
    draw.text((text_x + shadow_offset, 30 + shadow_offset), collection_display,
              fill=(0, 0, 0, 128), font=font_large)
    draw.text((text_x, 30), collection_display, fill=(255, 255, 255), font=font_large)

    # Draw number
    number_text = f"#{number:04d}"
    num_bbox = draw.textbbox((0, 0), number_text, font=font_large)
    num_width = num_bbox[2] - num_bbox[0]
    num_x = (IMG_SIZE - num_width) // 2

    draw.text((num_x + shadow_offset, IMG_SIZE - 60 + shadow_offset), number_text,
              fill=(0, 0, 0, 128), font=font_large)
    draw.text((num_x, IMG_SIZE - 60), number_text, fill=(255, 255, 255), font=font_large)

    # Add "DEMO" watermark
    demo_bbox = draw.textbbox((0, 0), "DEMO", font=font_small)
    demo_width = demo_bbox[2] - demo_bbox[0]
    demo_x = (IMG_SIZE - demo_width) // 2
    draw.text((demo_x, IMG_SIZE // 2 - 10), "DEMO",
              fill=(255, 255, 255, 100), font=font_small)

    # Save image
    filepath = os.path.join(output_dir, filename)
    img.save(filepath, 'PNG', optimize=True)
    print(f"  Created {filename}")

# Generate all images
print(f"Generating {sum(c[1] for c in collections)} demo NFT images...")

for collection_prefix, count, color in collections:
    print(f"\nGenerating {count} {collection_prefix} images...")
    for i in range(1, count + 1):
        filename = f"{collection_prefix}-{i}.png"
        create_nft_image(filename, collection_prefix, i, color)

print(f"\n✅ Successfully generated {sum(c[1] for c in collections)} demo NFT images in {output_dir}/")
print("\nImage counts by collection:")
for collection_prefix, count, _ in collections:
    print(f"  - {collection_prefix}: {count} images")
