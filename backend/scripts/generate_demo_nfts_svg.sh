#!/bin/bash
# Generate demo NFT placeholder SVG images

OUTPUT_DIR="frontend/static/demo-nfts"
mkdir -p "$OUTPUT_DIR"

# Function to create SVG placeholder
create_svg() {
    local filename=$1
    local title=$2
    local number=$3
    local color=$4

    cat > "$OUTPUT_DIR/$filename" << EOF
<svg width="400" height="400" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="grad_$number" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" style="stop-color:$color;stop-opacity:1" />
      <stop offset="100%" style="stop-color:rgb(50,50,50);stop-opacity:1" />
    </linearGradient>
  </defs>

  <!-- Background -->
  <rect width="400" height="400" fill="url(#grad_$number)"/>

  <!-- Decorative shapes -->
  <circle cx="$((100 + number * 17 % 200))" cy="$((100 + number * 13 % 200))" r="60" fill="rgba(255,255,255,0.1)"/>
  <rect x="$((50 + number * 23 % 250))" y="$((50 + number * 19 % 250))" width="80" height="80" fill="rgba(0,0,0,0.2)"/>

  <!-- Title -->
  <text x="200" y="60" font-family="Arial, sans-serif" font-size="28" font-weight="bold" text-anchor="middle" fill="white" stroke="black" stroke-width="1">
    $title
  </text>

  <!-- Number -->
  <text x="200" y="340" font-family="Arial, sans-serif" font-size="32" font-weight="bold" text-anchor="middle" fill="white" stroke="black" stroke-width="1">
    #$(printf "%04d" $number)
  </text>

  <!-- Demo watermark -->
  <text x="200" y="210" font-family="Arial, sans-serif" font-size="48" text-anchor="middle" fill="rgba(255,255,255,0.15)" font-weight="bold">
    DEMO
  </text>
</svg>
EOF

    echo "  Created $filename"
}

echo "Generating 55 demo NFT SVG images..."

# Clay Nation (15) - Blue
echo "Generating 15 clay-nation images..."
for i in {1..15}; do
    create_svg "clay-nation-$i.svg" "Clay Nation" $i "rgb(100,180,255)"
done

# Ape Society (8) - Orange
echo "Generating 8 ape-society images..."
for i in {1..8}; do
    create_svg "ape-society-$i.svg" "Ape Society" $i "rgb(255,180,100)"
done

# BAYC (12) - Purple
echo "Generating 12 bayc images..."
for i in {1..12}; do
    create_svg "bayc-$i.svg" "BAYC" $i "rgb(180,100,255)"
done

# SMB (20) - Pink
echo "Generating 20 smb images..."
for i in {1..20}; do
    create_svg "smb-$i.svg" "SMB" $i "rgb(255,100,150)"
done

echo ""
echo "✅ Successfully generated 55 demo NFT SVG images in $OUTPUT_DIR/"
echo ""
echo "Image counts by collection:"
echo "  - clay-nation: 15 images"
echo "  - ape-society: 8 images"
echo "  - bayc: 12 images"
echo "  - smb: 20 images"
