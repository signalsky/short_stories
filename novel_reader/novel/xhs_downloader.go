package novel

import (
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"time"
)

type XHSArticle struct {
	Title       string
	Keywords    string
	Description string
	ImageURLs   []string
}

func DownloadXHSArticle(url string) (string, error) {
	// 1. Fetch HTML
	client := &http.Client{
		Timeout: 30 * time.Second,
	}
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return "", fmt.Errorf("failed to create request: %v", err)
	}
	
	req.Header.Set("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
	
	resp, err := client.Do(req)
	if err != nil {
		return "", fmt.Errorf("failed to fetch URL: %v", err)
	}
	defer resp.Body.Close()
	
	if resp.StatusCode != 200 {
		return "", fmt.Errorf("server returned status: %d", resp.StatusCode)
	}

	bodyBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", fmt.Errorf("failed to read body: %v", err)
	}
	htmlContent := string(bodyBytes)

	// 2. Parse Metadata
	article := parseMetadata(htmlContent)
	if article.Title == "" {
		// Fallback: use timestamp if title not found
		article.Title = fmt.Sprintf("xhs_%d", time.Now().Unix())
	}
	
	// Clean up title for filename
	safeTitle := sanitizeFilename(article.Title)
	runes := []rune(safeTitle)
	if len(runes) > 50 {
		safeTitle = string(runes[:50])
	}
	
	baseDir := filepath.Join(".", safeTitle)
	if err := os.MkdirAll(baseDir, 0755); err != nil {
		return "", fmt.Errorf("failed to create directory: %v", err)
	}

	// 3. Save Text Info
	textFile := filepath.Join(baseDir, safeTitle+".txt")
	textContent := fmt.Sprintf("Title: %s\r\n\r\nKeywords: %s\r\n\r\nDescription: %s\r\n\r\nSource: %s\r\n", 
		article.Title, article.Keywords, article.Description, url)
	
	if err := os.WriteFile(textFile, []byte(textContent), 0644); err != nil {
		return "", fmt.Errorf("failed to write text file: %v", err)
	}

	// 4. Download Images
	// Use regex to find images in the HTML if not found in metadata
	// The metadata extraction might miss if it's not in og:image
	// But let's rely on parseMetadata for now.
	
	for i, imgURL := range article.ImageURLs {
		ext := ".jpg"
		if strings.Contains(imgURL, ".png") {
			ext = ".png"
		}
		
		filename := fmt.Sprintf("%d%s", i+1, ext)
		savePath := filepath.Join(baseDir, filename)
		
		// Ensure full URL
		if strings.HasPrefix(imgURL, "//") {
			imgURL = "https:" + imgURL
		} else if strings.HasPrefix(imgURL, "http://") {
			imgURL = "https://" + imgURL[7:]
		}
		
		if err := downloadFile(client, imgURL, savePath); err != nil {
			fmt.Printf("Warning: failed to download image %s: %v\n", imgURL, err)
		}
	}

	return baseDir, nil
}

func parseMetadata(html string) *XHSArticle {
	article := &XHSArticle{}
	
	// Extract Title
	reTitle := regexp.MustCompile(`<meta name="og:title" content="([^"]*)"`)
	match := reTitle.FindStringSubmatch(html)
	if len(match) > 1 {
		article.Title = match[1]
	} else {
		reTitleTag := regexp.MustCompile(`<title>(.*?)</title>`)
		matchTag := reTitleTag.FindStringSubmatch(html)
		if len(matchTag) > 1 {
			article.Title = matchTag[1]
		}
	}
	article.Title = strings.TrimSuffix(article.Title, " - 小红书")
	
	// Extract Keywords
	reKeywords := regexp.MustCompile(`<meta name="keywords" content="([^"]*)"`)
	match = reKeywords.FindStringSubmatch(html)
	if len(match) > 1 {
		article.Keywords = match[1]
	}
	
	// Extract Description
	reDesc := regexp.MustCompile(`<meta name="description" content="([^"]*)"`)
	match = reDesc.FindStringSubmatch(html)
	if len(match) > 1 {
		article.Description = match[1]
	}
	
	// Extract Images
	// XHS uses multiple og:image tags
	reImage := regexp.MustCompile(`<meta name="og:image" content="([^"]*)"`)
	matches := reImage.FindAllStringSubmatch(html, -1)
	seen := make(map[string]bool)
	for _, m := range matches {
		if len(m) > 1 {
			url := m[1]
			if !seen[url] {
				article.ImageURLs = append(article.ImageURLs, url)
				seen[url] = true
			}
		}
	}
	
	return article
}

func sanitizeFilename(name string) string {
	invalid := []string{"<", ">", ":", "\"", "/", "\\", "|", "?", "*", "\n", "\r", "\t"}
	for _, char := range invalid {
		name = strings.ReplaceAll(name, char, "_")
	}
	return strings.TrimSpace(name)
}

func downloadFile(client *http.Client, url string, destPath string) error {
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return err
	}
	
	req.Header.Set("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
	
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	
	if resp.StatusCode != 200 {
		return fmt.Errorf("status code %d", resp.StatusCode)
	}
	
	out, err := os.Create(destPath)
	if err != nil {
		return err
	}
	defer out.Close()
	
	_, err = io.Copy(out, resp.Body)
	return err
}
