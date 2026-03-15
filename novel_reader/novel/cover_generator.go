package novel

import (
	"fmt"
	"image"
	"image/color"

	"github.com/fogleman/gg"
)

// CoverGenerator handles the generation of cover images
type CoverGenerator struct {
	FontPath string
}

func NewCoverGenerator(fontPath string) *CoverGenerator {
	return &CoverGenerator{
		FontPath: fontPath,
	}
}

// GenerateCover creates a cover image with the given title and content
func (cg *CoverGenerator) GenerateCover(baseImagePath, title, content string, titleSize, contentSize float64) (image.Image, error) {
	// Load base image
	im, err := gg.LoadImage(baseImagePath)
	if err != nil {
		return nil, fmt.Errorf("failed to load base image: %v", err)
	}

	width := im.Bounds().Dx()
	height := im.Bounds().Dy()

	dc := gg.NewContext(width, height)
	dc.DrawImage(im, 0, 0)

	// Load font
	if err := dc.LoadFontFace(cg.FontPath, titleSize); err != nil {
		return nil, fmt.Errorf("failed to load font: %v", err)
	}

	// Draw Title (Centered)
	// Position: Top 25% of the image
	dc.SetColor(color.Black) // Default to black text
	titleY := float64(height) * 0.25
	dc.DrawStringAnchored(title, float64(width)/2, titleY, 0.5, 0.5)

	// Draw Content (Left Aligned)
	// Position: Starts at Top 45%, Left margin 10%
	contentY := float64(height) * 0.45
	margin := float64(width) * 0.1
	maxWidth := float64(width) - 2*margin
	
	// Smaller font for content
	if err := dc.LoadFontFace(cg.FontPath, contentSize); err != nil {
		return nil, fmt.Errorf("failed to load content font: %v", err)
	}

	lines := dc.WordWrap(content, maxWidth)
	lineHeight := 1.8 * contentSize // 1.8 line spacing

	for i, line := range lines {
		dc.DrawString(line, margin, contentY+float64(i)*lineHeight)
	}

	return dc.Image(), nil
}
