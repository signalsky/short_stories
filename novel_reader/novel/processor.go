package novel

import (
	"fmt"
	"image"
	"image/jpeg"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"

	"github.com/fogleman/gg"
)

type NovelProcessor struct {
	Content        string
	Pages          []string
	CurrentPage    int
	TotalPages     int
	FontPath       string
	BackgroundPath string
	FontSize       float64
	TitleFontSize  float64
	LineSpacing    float64
	Title          string // For file naming and display
	
	// Dimensions for the "phone" view
	Width  int
	Height int
	
	// Text bounds (padding)
	PaddingLeft   float64
	PaddingRight  float64
	PaddingTop    float64
	PaddingBottom float64
}

func NewNovelProcessor() *NovelProcessor {
	return &NovelProcessor{
		Width:         1080,
		Height:        1440,
		FontSize:      48, // Reasonable for 1080p width phone
		TitleFontSize: 72, // Larger font for title
		LineSpacing:   1.5,
		PaddingLeft:   80,
		PaddingRight:  80,
		PaddingTop:    150,
		PaddingBottom: 100, // Reduced from 150 to allow more lines
		BackgroundPath: "background.png",
	}
}

func (np *NovelProcessor) LoadFont(possiblePaths []string) error {
	for _, path := range possiblePaths {
		if _, err := os.Stat(path); err == nil {
			np.FontPath = path
			return nil
		}
	}
	return fmt.Errorf("no suitable font found")
}

func (np *NovelProcessor) LoadFromURL(urlStr string) error {
	resp, err := http.Get(urlStr)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return err
	}
	np.Content = string(body)
	
	// Title should be set by UI before calling this or extracted here
	// The current requirement is mandatory title input, so we assume np.Title is set externally if empty.
	// But if we want to fallback:
	if np.Title == "" {
		parts := strings.Split(urlStr, "?")
		pathParts := strings.Split(parts[0], "/")
		if len(pathParts) > 0 {
			np.Title = pathParts[len(pathParts)-1]
		} else {
			np.Title = "downloaded_novel"
		}
	}
	
	return np.Paginate()
}

func (np *NovelProcessor) LoadFromFile(path string) error {
	content, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	np.Content = string(content)
	
	// Title is set by UI
	if np.Title == "" {
		base := filepath.Base(path)
		ext := filepath.Ext(base)
		np.Title = strings.TrimSuffix(base, ext)
	}
	
	return np.Paginate()
}

func (np *NovelProcessor) SaveToFile(path string) error {
	return os.WriteFile(path, []byte(np.Content), 0644)
}

// Paginate calculates pages based on current settings
func (np *NovelProcessor) Paginate() error {
	if np.Content == "" {
		np.Pages = []string{}
		np.TotalPages = 0
		return nil
	}
	
	if np.FontPath == "" {
		return fmt.Errorf("font not loaded")
	}

	dc := gg.NewContext(np.Width, np.Height)
	if err := dc.LoadFontFace(np.FontPath, np.FontSize); err != nil {
		return err
	}

	// Calculate max width for text
	maxWidth := float64(np.Width) - np.PaddingLeft - np.PaddingRight
	
	// Split content into paragraphs
	// Windows uses \r\n, Linux \n. Normalize.
	text := strings.ReplaceAll(np.Content, "\r\n", "\n")
	paragraphs := strings.Split(text, "\n")
	
	var pages []string
	var currentLines []string
	
	// Initial height calculation for first page
	// First page has Title.
	// We need to measure Title height.
	// Note: We don't write the title into "pages" string array, we just reserve space.
	// GetPageImage will draw the title separately.
	
	// Measure Title
	titleHeight := 0.0
	if np.Title != "" {
		// Load title font to measure
		if err := dc.LoadFontFace(np.FontPath, np.TitleFontSize); err == nil {
			// Wrap title if needed? Assume single line or wrap
			// Let's assume title might wrap
			titleLines := dc.WordWrap(np.Title, maxWidth)
			titleHeight = float64(len(titleLines)) * np.TitleFontSize * 1.5 // 1.5 spacing
			// Reset font
			dc.LoadFontFace(np.FontPath, np.FontSize)
		}
	}
	
	// Start with Title offset on first page
	currentHeight := titleHeight + np.FontSize // Add extra gap after title
	lineHeight := np.FontSize * np.LineSpacing
	maxHeight := float64(np.Height) - np.PaddingTop - np.PaddingBottom

	for _, para := range paragraphs {
		// Custom wrap for Chinese support (gg.WordWrap splits by space)
		lines := np.WrapText(para, maxWidth, dc)
		
		// If paragraph is empty (empty line), add a blank line
		if len(lines) == 0 {
			lines = []string{""}
		}

		for _, line := range lines {
			if currentHeight+lineHeight > maxHeight {
				// Page full
				pages = append(pages, strings.Join(currentLines, "\n"))
				currentLines = []string{}
				currentHeight = 0
			}
			currentLines = append(currentLines, line)
			currentHeight += lineHeight
		}
	}
	
	// Add last page
	if len(currentLines) > 0 {
		pages = append(pages, strings.Join(currentLines, "\n"))
	}
	
	np.Pages = pages
	np.TotalPages = len(pages)
	np.CurrentPage = 0 // Reset to first page
	
	return nil
}

// WrapText handles character-based wrapping for Chinese text
func (np *NovelProcessor) WrapText(text string, maxWidth float64, dc *gg.Context) []string {
	var lines []string
	var currentLine strings.Builder
	
	runes := []rune(text)
	for _, r := range runes {
		testStr := currentLine.String() + string(r)
		w, _ := dc.MeasureString(testStr)
		
		if w > maxWidth {
			// Line full
			if currentLine.Len() > 0 {
				lines = append(lines, currentLine.String())
				currentLine.Reset()
			}
			currentLine.WriteRune(r)
		} else {
			currentLine.WriteRune(r)
		}
	}
	if currentLine.Len() > 0 {
		lines = append(lines, currentLine.String())
	}
	return lines
}

func (np *NovelProcessor) GetPageImage(pageIndex int) (image.Image, error) {
	if pageIndex < 0 || pageIndex >= len(np.Pages) {
		return nil, fmt.Errorf("index out of bounds")
	}

	dc := gg.NewContext(np.Width, np.Height)
	
	// Draw background
	bg, err := gg.LoadImage(np.BackgroundPath)
	if err == nil {
		dc.DrawImage(bg, 0, 0)
	} else {
		dc.SetRGB(1, 1, 1)
		dc.Clear()
	}
	
	dc.SetRGB(0, 0, 0) // Black text
	
	y := np.PaddingTop + np.FontSize // Baseline
	
	// Draw Title on First Page
	if pageIndex == 0 && np.Title != "" {
		if err := dc.LoadFontFace(np.FontPath, np.TitleFontSize); err == nil {
			titleLines := dc.WordWrap(np.Title, float64(np.Width)-np.PaddingLeft-np.PaddingRight)
			titleLineHeight := np.TitleFontSize * 1.5
			
			// Draw title centered? Or left?
			// Let's do Left aligned as per regular text but maybe Bold if font supported (we only have one font file though)
			
			for _, line := range titleLines {
				dc.DrawString(line, np.PaddingLeft, np.PaddingTop+np.TitleFontSize) // Adjust baseline
				y += titleLineHeight
			}
			y += np.FontSize // Extra gap
		}
		// Reset Font
		dc.LoadFontFace(np.FontPath, np.FontSize)
	} else {
		// Ensure font is loaded for normal pages
		if err := dc.LoadFontFace(np.FontPath, np.FontSize); err != nil {
			return nil, err
		}
	}
	
	lines := strings.Split(np.Pages[pageIndex], "\n")
	x := np.PaddingLeft
	
	lineHeight := np.FontSize * np.LineSpacing
	
	for _, line := range lines {
		dc.DrawString(line, x, y)
		y += lineHeight
	}
	
	return dc.Image(), nil
}

func (np *NovelProcessor) BatchExportImages(count int, outputDir string) error {
	if count > np.TotalPages {
		count = np.TotalPages
	}
	
	if _, err := os.Stat(outputDir); os.IsNotExist(err) {
		if err := os.MkdirAll(outputDir, 0755); err != nil {
			return err
		}
	}

	for i := 0; i < count; i++ {
		img, err := np.GetPageImage(i)
		if err != nil {
			return err
		}
		
		filename := filepath.Join(outputDir, fmt.Sprintf("%d.jpg", i+1))
		f, err := os.Create(filename)
		if err != nil {
			return err
		}
		defer f.Close()
		
		// Quality 90
		if err := jpeg.Encode(f, img, &jpeg.Options{Quality: 90}); err != nil {
			return err
		}
	}
	return nil
}
