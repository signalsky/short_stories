package ui

import (
	"bytes"
	"encoding/json"
	"fmt"
	"image"
	"image/png"
	"io"
	"mime/multipart"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"

	"novel_reader/novel"

	"github.com/lxn/walk"
	. "github.com/lxn/walk/declarative"
)

type NovelApp struct {
	MainWindow *walk.MainWindow
	Processor  *novel.NovelProcessor

	// UI Components
	ContentComposite *walk.Composite
	NovelComposite   *walk.Composite
	
	// Novel View
	ImageView     *walk.ImageView
	TextEdit      *walk.TextEdit
	PageLabel     *walk.Label
	PrevBtn       *walk.PushButton
	NextBtn       *walk.PushButton
	EditBtn       *walk.PushButton
	ResolutionCB  *walk.ComboBox
	
	// Cover View
	CoverComposite    *walk.Composite
	CoverTitleInput   *walk.LineEdit
	CoverTitleSizeInput *walk.LineEdit
	CoverContentInput *walk.TextEdit
	CoverContentSizeInput *walk.LineEdit
	CoverImageView    *walk.ImageView
	LastCoverImage    image.Image
	CoverSelectedImage string
	CoverThumbComposites []*walk.Composite
	
	// Downloader View
	DownloaderComposite *walk.Composite
	DownloadUrlInput    *walk.LineEdit
	DownloadLog         *walk.TextEdit
	LastDownloadDir     string

	// State
	IsEditing bool
}

const ocrBeginMarker = "[OCR_PARSE_BEGIN]"
const ocrEndMarker = "[OCR_PARSE_END]"

func NewNovelApp() *NovelApp {
	processor := novel.NewNovelProcessor()
	
	// Try to load font
	fonts := []string{
		"C:\\Windows\\Fonts\\simkai.ttf", // KaiTi (楷体) - More elegant/xiuqi
		"C:\\Windows\\Fonts\\simfang.ttf", // FangSong (仿宋)
		"C:\\Windows\\Fonts\\msyh.ttc",
		"C:\\Windows\\Fonts\\msyh.ttf",
		"C:\\Windows\\Fonts\\simhei.ttf",
		"C:\\Windows\\Fonts\\arial.ttf",
	}
	if err := processor.LoadFont(fonts); err != nil {
		fmt.Println("Warning: No suitable font found for export rendering:", err)
	}

	return &NovelApp{
		Processor: processor,
	}
}

func (app *NovelApp) Run() {
	icon, err := walk.NewIconFromFile("icon.ico")
	if err != nil {
		fmt.Println("Warning: Failed to load icon:", err)
	}

	if _, err := (MainWindow{
		AssignTo: &app.MainWindow, // Assign directly to prevent nil panic in handlers
		Title:    "灼见阅读",
		Icon:     icon,
		Size:     Size{Width: 1200, Height: 900},
		Layout:   HBox{MarginsZero: true, SpacingZero: true}, // Remove gaps for cleaner look 
		Children: []Widget{
			// Sidebar (Fixed width, Left aligned)
			Composite{
				Layout:     VBox{Margins: Margins{Left: 10, Top: 10, Right: 10, Bottom: 10}, Spacing: 10},
				MaxSize:    Size{Width: 200, Height: 0}, // Width 200, Height unlimited
				Background: SolidColorBrush{Color: walk.RGB(240, 240, 240)}, // Light Gray
				Children: []Widget{
					VSpacer{Size: 10},
					PushButton{
						Text: "小说阅读",
						OnClicked: func() {
							app.showNovelView()
						},
					},
					PushButton{
						Text: "首图生成",
						OnClicked: func() {
							app.showCoverView()
						},
					},
					PushButton{
						Text: "下载文章",
						OnClicked: func() {
							app.showDownloaderView()
						},
					},
					PushButton{
						Text: "其他",
						OnClicked: func() {
							app.showPlaceholder()
						},
					},
					VSpacer{}, // Push content to top
				},
			},
			// Content Area (Fills remaining space)
			Composite{
				AssignTo:      &app.ContentComposite,
				Layout:        HBox{MarginsZero: true}, // Use HBox for internal Novel View
				StretchFactor: 1, // Fill remaining width
				Children:      []Widget{}, // Initially empty, populated by createNovelView
			},
		},
		OnSizeChanged: func() {
			// Trigger initial view creation once window is ready
			// But OnSizeChanged happens many times.
			// Better to just call createNovelView after Run? No, Run blocks.
			// We can check if created.
			if app.NovelComposite == nil {
				app.showNovelView()
			}
		},
	}).Run(); err != nil {
		fmt.Println(err)
	}
}

func (app *NovelApp) showPlaceholder() {
	if app.NovelComposite != nil {
		app.NovelComposite.SetVisible(false)
	}
	if app.CoverComposite != nil {
		app.CoverComposite.SetVisible(false)
	}
	if app.DownloaderComposite != nil {
		app.DownloaderComposite.SetVisible(false)
	}
}

func (app *NovelApp) showNovelView() {
	if app.CoverComposite != nil {
		app.CoverComposite.SetVisible(false)
	}
	if app.DownloaderComposite != nil {
		app.DownloaderComposite.SetVisible(false)
	}
	if app.NovelComposite == nil {
		app.createNovelView()
	} else {
		app.NovelComposite.SetVisible(true)
	}
	app.updateReadingView()
}

func (app *NovelApp) showDownloaderView() {
	if app.NovelComposite != nil {
		app.NovelComposite.SetVisible(false)
	}
	if app.CoverComposite != nil {
		app.CoverComposite.SetVisible(false)
	}
	if app.DownloaderComposite == nil {
		app.createDownloaderView()
	} else {
		app.DownloaderComposite.SetVisible(true)
	}
}

func (app *NovelApp) createDownloaderView() {
	if app.ContentComposite == nil {
		return
	}

	builder := NewBuilder(app.ContentComposite)
	
	Composite{
		AssignTo: &app.DownloaderComposite,
		Layout:   HBox{Margins: Margins{Left: 10, Top: 10, Right: 10, Bottom: 10}},
		Children: []Widget{
			Composite{
				Layout: VBox{Margins: Margins{Left: 10, Top: 10, Right: 10, Bottom: 10}},
				Children: []Widget{
					Label{
						Text: "小红书文章链接:",
						Font: Font{PointSize: 12, Bold: true},
					},
					LineEdit{
						AssignTo: &app.DownloadUrlInput,
						MinSize:  Size{Height: 30},
					},
					VSpacer{Size: 10},
					Label{Text: "下载日志:"},
					TextEdit{
						AssignTo: &app.DownloadLog,
						ReadOnly: true,
						VScroll:  true,
					},
				},
			},
			Composite{
				Layout:  VBox{Margins: Margins{Left: 10}},
				MaxSize: Size{Width: 150},
				Children: []Widget{
					PushButton{
						Text:      "开始下载",
						OnClicked: app.handleDownload,
					},
					PushButton{
						Text:      "解析文字",
						OnClicked: app.handleParseOCR,
					},
					PushButton{
						Text: "清空日志",
						OnClicked: func() {
							if app.DownloadLog != nil {
								app.DownloadLog.SetText("")
							}
						},
					},
					VSpacer{},
				},
			},
		},
	}.Create(builder)
}

func (app *NovelApp) handleDownload() {
	url := app.DownloadUrlInput.Text()
	if url == "" {
		walk.MsgBox(app.MainWindow, "错误", "请输入链接", walk.MsgBoxIconError)
		return
	}
	
	app.log("开始下载: " + url)
	
	go func() {
		dir, err := novel.DownloadXHSArticle(url)
		
		app.MainWindow.Synchronize(func() {
			if err != nil {
				app.log("下载失败: " + err.Error())
				walk.MsgBox(app.MainWindow, "错误", "下载失败: "+err.Error(), walk.MsgBoxIconError)
			} else {
				app.log("下载成功! 保存至: " + dir)
				app.LastDownloadDir = dir
				walk.MsgBox(app.MainWindow, "成功", "下载完成\n保存目录: "+dir, walk.MsgBoxIconInformation)
				app.DownloadUrlInput.SetText("")
			}
		})
	}()
}

func (app *NovelApp) log(msg string) {
	if app.DownloadLog != nil {
		app.DownloadLog.AppendText(msg + "\r\n")
	}
}

func (app *NovelApp) handleParseOCR() {
	if app.LastDownloadDir == "" {
		walk.MsgBox(app.MainWindow, "提示", "请先下载文章", walk.MsgBoxIconInformation)
		return
	}

	textFile, err := findArticleTextFile(app.LastDownloadDir)
	if err != nil {
		walk.MsgBox(app.MainWindow, "错误", "读取目录失败: "+err.Error(), walk.MsgBoxIconError)
		return
	}

	parsed, err := hasOCRSection(textFile)
	if err != nil {
		walk.MsgBox(app.MainWindow, "错误", "读取文本失败: "+err.Error(), walk.MsgBoxIconError)
		return
	}

	if parsed {
		ret := walk.MsgBox(app.MainWindow, "重复解析", "检测到已解析内容，是否覆盖重写？", walk.MsgBoxYesNo|walk.MsgBoxIconQuestion)
		if ret != walk.DlgCmdYes {
			return
		}
	}

	app.log("开始解析图片文字: " + app.LastDownloadDir)

	go func(dir, txtPath string) {
		if !isOCRServiceRunning() {
			app.MainWindow.Synchronize(func() {
				app.log("ocr服务没开启")
				walk.MsgBox(app.MainWindow, "错误", "ocr服务没开启", walk.MsgBoxIconError)
			})
			return
		}

		parsedText, imageCount, err := parseOCRFromImages(dir, func(current, total int, imageName string) {
			app.MainWindow.Synchronize(func() {
				app.log(fmt.Sprintf("解析进度: %d/%d (%s)", current, total, imageName))
			})
		})
		if err != nil {
			app.MainWindow.Synchronize(func() {
				app.log("解析失败: " + err.Error())
				walk.MsgBox(app.MainWindow, "错误", "解析失败: "+err.Error(), walk.MsgBoxIconError)
			})
			return
		}

		if err := writeOCRSection(txtPath, parsedText); err != nil {
			app.MainWindow.Synchronize(func() {
				app.log("写入失败: " + err.Error())
				walk.MsgBox(app.MainWindow, "错误", "写入失败: "+err.Error(), walk.MsgBoxIconError)
			})
			return
		}

		app.MainWindow.Synchronize(func() {
			app.log(fmt.Sprintf("解析完成，共处理%d张图片", imageCount))
			app.log("文字已写入: " + txtPath)
			walk.MsgBox(app.MainWindow, "成功", "解析完成，文字已写入txt", walk.MsgBoxIconInformation)
		})
	}(app.LastDownloadDir, textFile)
}

func isOCRServiceRunning() bool {
	client := &http.Client{Timeout: 2 * time.Second}
	resp, err := client.Get("http://127.0.0.1:8000/docs")
	if err != nil {
		return false
	}
	defer resp.Body.Close()
	return resp.StatusCode >= 200 && resp.StatusCode < 500
}

func findArticleTextFile(dir string) (string, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return "", err
	}

	var txtFiles []string
	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}
		if strings.EqualFold(filepath.Ext(entry.Name()), ".txt") {
			txtFiles = append(txtFiles, entry.Name())
		}
	}

	if len(txtFiles) > 0 {
		sort.Strings(txtFiles)
		return filepath.Join(dir, txtFiles[0]), nil
	}

	return filepath.Join(dir, filepath.Base(dir)+".txt"), nil
}

func hasOCRSection(path string) (bool, error) {
	content, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return false, nil
		}
		return false, err
	}
	text := string(content)
	return strings.Contains(text, ocrBeginMarker) && strings.Contains(text, ocrEndMarker), nil
}

func parseOCRFromImages(dir string, onProgress func(current, total int, imageName string)) (string, int, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return "", 0, err
	}

	var images []string
	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}
		ext := strings.ToLower(filepath.Ext(entry.Name()))
		if ext == ".jpg" || ext == ".jpeg" || ext == ".png" {
			images = append(images, entry.Name())
		}
	}

	if len(images) == 0 {
		return "", 0, fmt.Errorf("未找到可解析图片")
	}

	sort.Slice(images, func(i, j int) bool {
		aBase := strings.TrimSuffix(images[i], filepath.Ext(images[i]))
		bBase := strings.TrimSuffix(images[j], filepath.Ext(images[j]))
		aNum, aErr := strconv.Atoi(aBase)
		bNum, bErr := strconv.Atoi(bBase)
		if aErr == nil && bErr == nil {
			return aNum < bNum
		}
		if aErr == nil {
			return true
		}
		if bErr == nil {
			return false
		}
		return strings.ToLower(images[i]) < strings.ToLower(images[j])
	})

	var builder strings.Builder
	total := len(images)
	for i, imageName := range images {
		if onProgress != nil {
			onProgress(i+1, total, imageName)
		}
		imagePath := filepath.Join(dir, imageName)
		text, err := requestOCRText(imagePath)
		if err != nil {
			return "", 0, fmt.Errorf("%s 解析失败: %v", imageName, err)
		}

		builder.WriteString("[" + imageName + "]\r\n")
		if strings.TrimSpace(text) == "" {
			builder.WriteString("(空结果)\r\n\r\n")
			continue
		}
		builder.WriteString(text + "\r\n\r\n")
	}

	return strings.TrimSpace(builder.String()), len(images), nil
}

func requestOCRText(imagePath string) (string, error) {
	file, err := os.Open(imagePath)
	if err != nil {
		return "", err
	}
	defer file.Close()

	var body bytes.Buffer
	writer := multipart.NewWriter(&body)
	part, err := writer.CreateFormFile("file", filepath.Base(imagePath))
	if err != nil {
		return "", err
	}
	if _, err := io.Copy(part, file); err != nil {
		return "", err
	}
	if err := writer.Close(); err != nil {
		return "", err
	}

	req, err := http.NewRequest("POST", "http://127.0.0.1:8000/ocr", &body)
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", writer.FormDataContentType())

	client := &http.Client{Timeout: 60 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		respBody, _ := io.ReadAll(resp.Body)
		return "", fmt.Errorf("OCR请求失败(%d): %s", resp.StatusCode, strings.TrimSpace(string(respBody)))
	}

	var result struct {
		Status   string `json:"status"`
		FullText string `json:"full_text"`
		Detail   string `json:"detail"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return "", err
	}

	if result.Status != "" && result.Status != "success" {
		if result.Detail != "" {
			return "", fmt.Errorf(result.Detail)
		}
		return "", fmt.Errorf("OCR服务返回失败状态")
	}

	return strings.TrimSpace(result.FullText), nil
}

func writeOCRSection(path, parsedText string) error {
	var current string
	content, err := os.ReadFile(path)
	if err != nil {
		if !os.IsNotExist(err) {
			return err
		}
	} else {
		current = string(content)
	}

	re := regexp.MustCompile(`(?s)\r?\n?\[OCR_PARSE_BEGIN\].*?\[OCR_PARSE_END\]\r?\n?`)
	cleaned := strings.TrimSpace(re.ReplaceAllString(current, ""))

	section := ocrBeginMarker + "\r\n" + time.Now().Format("2006-01-02 15:04:05") + "\r\n" + parsedText + "\r\n" + ocrEndMarker
	if cleaned == "" {
		return os.WriteFile(path, []byte(section+"\r\n"), 0644)
	}
	return os.WriteFile(path, []byte(cleaned+"\r\n\r\n"+section+"\r\n"), 0644)
}

func (app *NovelApp) createNovelView() {
	if app.ContentComposite == nil {
		return
	}

	builder := NewBuilder(app.ContentComposite)
	
	err := Composite{
		AssignTo: &app.NovelComposite,
		Layout:   HBox{Margins: Margins{Left: 10, Top: 10, Right: 10, Bottom: 10}},
		Children: []Widget{
			// Reading Area (Stack: Image + TextEdit)
			Composite{
				Layout: HBox{MarginsZero: true}, 
				Children: []Widget{
					ImageView{
						AssignTo: &app.ImageView,
						Mode:     ImageViewModeZoom, 
						MinSize:  Size{Width: 367, Height: 638}, // Half of 734x1276 for display
					},
					TextEdit{
						AssignTo:  &app.TextEdit,
						Visible:   false,
						VScroll:   true, 
					},
				},
			},
			// Buttons (Right Side)
			Composite{
				Layout: VBox{Margins: Margins{Left: 10}}, // Add left margin
				MaxSize: Size{Width: 150},
				Children: []Widget{
					Label{Text: "分辨率:"},
					ComboBox{
						AssignTo:      &app.ResolutionCB,
						Model:         []string{"734x1276", "1080x1440"},
						CurrentIndex:  0, // Default 734x1276
						OnCurrentIndexChanged: app.handleResolutionChange,
					},
					VSpacer{Size: 10},
					Label{
						AssignTo: &app.PageLabel,
						Text:     "Page: 0/0",
						TextAlignment: AlignCenter,
					},
					PushButton{
						AssignTo: &app.PrevBtn,
						Text:     "上一页",
						OnClicked: func() {
							if app.Processor.CurrentPage > 0 {
								app.Processor.CurrentPage--
								app.updateReadingView()
							}
						},
					},
					PushButton{
						AssignTo: &app.NextBtn,
						Text:     "下一页",
						OnClicked: func() {
							if app.Processor.CurrentPage < app.Processor.TotalPages-1 {
								app.Processor.CurrentPage++
								app.updateReadingView()
							}
						},
					},
					VSpacer{Size: 10},
					PushButton{
						Text: "截图",
						OnClicked: app.handleScreenshot,
					},
					PushButton{
						Text: "导入",
						OnClicked: app.handleImport,
					},
					PushButton{
						Text: "设置背景",
						OnClicked: app.handleSetBackground,
					},
					PushButton{
						AssignTo: &app.EditBtn,
						Text:     "编辑",
						OnClicked: app.toggleEdit,
					},
					VSpacer{}, // Push buttons to top
				},
			},
		},
	}.Create(builder)
	
	if err != nil {
		fmt.Println("Error creating novel view:", err)
	}
}

func (app *NovelApp) handleResolutionChange() {
	if app.ResolutionCB == nil || app.Processor == nil {
		return
	}
	
	idx := app.ResolutionCB.CurrentIndex()
	switch idx {
	case 0: // 734x1276
		app.Processor.Width = 734
		app.Processor.Height = 1276
		app.Processor.FontSize = 32
		app.Processor.TitleFontSize = 48
		app.Processor.PaddingLeft = 50
		app.Processor.PaddingRight = 50
		app.Processor.PaddingTop = 100
		app.Processor.PaddingBottom = 30
		
		// Update ImageView size
		if app.ImageView != nil {
			app.ImageView.SetMinMaxSize(walk.Size{Width: 367, Height: 638}, walk.Size{})
		}
		
	case 1: // 1080x1440
		app.Processor.Width = 1080
		app.Processor.Height = 1440
		app.Processor.FontSize = 48
		app.Processor.TitleFontSize = 72
		app.Processor.PaddingLeft = 80
		app.Processor.PaddingRight = 80
		app.Processor.PaddingTop = 150
		app.Processor.PaddingBottom = 50
		
		// Update ImageView size
		if app.ImageView != nil {
			app.ImageView.SetMinMaxSize(walk.Size{Width: 540, Height: 720}, walk.Size{})
		}
	}
	
	// Repaginate and update view
	if err := app.Processor.Paginate(); err != nil {
		fmt.Println("Error repaginating:", err)
	}
	app.updateReadingView()
}

func (app *NovelApp) updateReadingView() {
	if app.Processor.TotalPages == 0 {
		if app.PageLabel != nil {
			app.PageLabel.SetText("Page: 0/0")
		}
		if app.ImageView != nil {
			app.ImageView.SetImage(nil)
		}
		return
	}
	
	if app.PageLabel != nil {
		app.PageLabel.SetText(fmt.Sprintf("Page: %d/%d\nWords: %d", 
			app.Processor.CurrentPage+1, 
			app.Processor.TotalPages,
			utf8.RuneCountInString(app.Processor.Content),
		))
	}
	
	img, err := app.Processor.GetPageImage(app.Processor.CurrentPage)
	if err != nil {
		fmt.Println("Error rendering:", err)
		return
	}
	
	bitmap, err := walk.NewBitmapFromImage(img)
	if err != nil {
		fmt.Println("Error converting image:", err)
		return
	}
	
	if app.ImageView != nil {
		app.ImageView.SetImage(bitmap)
	}
}

func (app *NovelApp) handleImport() {
	if app.MainWindow == nil {
		fmt.Println("MainWindow is nil")
		return
	}
	
	// If currently editing, switch back to view mode first
	if app.IsEditing {
		app.toggleEdit()
	}

	var dlg *walk.Dialog
	var urlTE *walk.TextEdit
	var titleTE *walk.TextEdit
	
	icon, _ := walk.NewIconFromFile("icon.ico")
	
	Dialog{
		AssignTo: &dlg,
		Title:    "导入小说",
		Icon:     icon,
		MinSize:  Size{Width: 500, Height: 250}, // Reduced height
		Layout:   VBox{},
		Children: []Widget{
			Label{Text: "小说标题 (必填):"},
			TextEdit{AssignTo: &titleTE},
			VSpacer{Size: 10},
			PushButton{
				Text: "从文件导入",
				OnClicked: func() {
					title := titleTE.Text()
					if title == "" {
						walk.MsgBox(dlg, "错误", "标题不能为空", walk.MsgBoxIconError)
						return
					}
					
					dlg.Close(walk.DlgCmdOK) 
					dlgFile := new(walk.FileDialog)
					dlgFile.Filter = "Text Files (*.txt)|*.txt|All Files (*.*)|*.*"
					if ok, err := dlgFile.ShowOpen(app.MainWindow); err != nil {
						return
					} else if ok {
						app.Processor.Title = title
						if err := app.Processor.LoadFromFile(dlgFile.FilePath); err != nil {
							walk.MsgBox(app.MainWindow, "错误", err.Error(), walk.MsgBoxIconError)
						} else {
							app.updateReadingView()
						}
					}
				},
			},
			VSpacer{Size: 10},
			Label{Text: "或者输入链接 (支持长链接):"},
			TextEdit{
				AssignTo: &urlTE,
				MinSize:  Size{Height: 40}, // Smaller URL box
			},
			Composite{
				Layout: HBox{},
				Children: []Widget{
					HSpacer{},
					PushButton{
						Text: "从链接导入",
						OnClicked: func() {
							title := titleTE.Text()
							if title == "" {
								walk.MsgBox(dlg, "错误", "标题不能为空", walk.MsgBoxIconError)
								return
							}
							
							url := urlTE.Text()
							if url != "" {
								dlg.Close(walk.DlgCmdOK)
								app.Processor.Title = title
								if err := app.Processor.LoadFromURL(url); err != nil {
									walk.MsgBox(app.MainWindow, "错误", err.Error(), walk.MsgBoxIconError)
								} else {
									app.updateReadingView()
								}
							}
						},
					},
				},
			},
		},
	}.Run(app.MainWindow)
}

func (app *NovelApp) handleSetBackground() {
	if app.MainWindow == nil { return }
	
	dlg := new(walk.FileDialog)
	dlg.Filter = "Images (*.png;*.jpg)|*.png;*.jpg"
	if ok, err := dlg.ShowOpen(app.MainWindow); err != nil {
		return
	} else if ok {
		app.Processor.BackgroundPath = dlg.FilePath
		app.updateReadingView()
	}
}

func (app *NovelApp) handleScreenshot() {
	if app.MainWindow == nil { return }

	var dlg *walk.Dialog
	var pageTE *walk.TextEdit
	
	Dialog{
		AssignTo: &dlg,
		Title:    "导出截图",
		MinSize:  Size{Width: 200, Height: 100},
		Layout:   VBox{},
		Children: []Widget{
			Label{Text: "截图页数:"},
			TextEdit{AssignTo: &pageTE, Text: "5"},
			PushButton{
				Text: "导出",
				OnClicked: func() {
					count, err := strconv.Atoi(pageTE.Text())
					if err != nil {
						walk.MsgBox(dlg, "错误", "无效的数字", walk.MsgBoxIconError)
						return
					}
					
					folderName := app.Processor.Title
					if folderName == "" {
						folderName = "output"
					}
					
					dlg.Close(walk.DlgCmdOK)
					
					go func() {
						err := app.Processor.BatchExportImages(count, folderName)
						app.MainWindow.Synchronize(func() {
							if err != nil {
								walk.MsgBox(app.MainWindow, "错误", err.Error(), walk.MsgBoxIconError)
							} else {
								walk.MsgBox(app.MainWindow, "成功", "导出完成，保存至 "+folderName, walk.MsgBoxIconInformation)
							}
						})
					}()
				},
			},
		},
	}.Run(app.MainWindow)
}

func (app *NovelApp) toggleEdit() {
	if app.IsEditing {
		// Save
		app.Processor.Content = app.TextEdit.Text()
		if err := app.Processor.Paginate(); err != nil {
			walk.MsgBox(app.MainWindow, "Error", err.Error(), walk.MsgBoxIconError)
		}
		
		filename := app.Processor.Title + ".txt"
		if err := app.Processor.SaveToFile(filename); err != nil {
			walk.MsgBox(app.MainWindow, "Error", err.Error(), walk.MsgBoxIconError)
		}
		
		app.IsEditing = false
		app.EditBtn.SetText("编辑")
		app.TextEdit.SetVisible(false)
		app.ImageView.SetVisible(true)
		app.updateReadingView()
	} else {
		// Edit
		app.IsEditing = true
		app.EditBtn.SetText("保存")
		app.TextEdit.SetText(app.Processor.Content)
		app.ImageView.SetVisible(false)
		app.TextEdit.SetVisible(true)
	}
}

func (app *NovelApp) showCoverView() {
	if app.NovelComposite != nil {
		app.NovelComposite.SetVisible(false)
	}
	if app.DownloaderComposite != nil {
		app.DownloaderComposite.SetVisible(false)
	}
	if app.CoverComposite == nil {
		app.createCoverView()
	} else {
		app.CoverComposite.SetVisible(true)
	}
}

func (app *NovelApp) createCoverView() {
	if app.ContentComposite == nil {
		return
	}

	// List images in relative path "首图"
	imageDir := "首图"
	var imageFiles []string
	entries, err := os.ReadDir(imageDir)
	if err == nil {
		for _, entry := range entries {
			if !entry.IsDir() {
				ext := filepath.Ext(entry.Name())
				if ext == ".png" || ext == ".jpg" {
					imageFiles = append(imageFiles, entry.Name())
				}
			}
		}
	} else {
		// Fallback to absolute path if relative fails (e.g. running from different dir)
		imageDir = "e:\\worksapce\\short_stories\\novel_reader\\首图"
		entries, err = os.ReadDir(imageDir)
		if err == nil {
			for _, entry := range entries {
				if !entry.IsDir() {
					ext := filepath.Ext(entry.Name())
					if ext == ".png" || ext == ".jpg" {
						imageFiles = append(imageFiles, entry.Name())
					}
				}
			}
		} else {
			fmt.Println("Error reading image directory:", err)
		}
	}
	
	// Prepare thumbnail widgets
	app.CoverThumbComposites = make([]*walk.Composite, len(imageFiles))
	var thumbWidgets []Widget
	
	for i, file := range imageFiles {
		idx := i
		name := file
		fullPath := filepath.Join(imageDir, name)
		
		// Determine initial background color
		bgColor := walk.RGB(240, 240, 240)
		if i == 0 {
			bgColor = walk.RGB(173, 216, 230) // Selected
			app.CoverSelectedImage = name
		}
		
		thumbWidgets = append(thumbWidgets, Composite{
			AssignTo: &app.CoverThumbComposites[idx],
			Layout: VBox{Margins: Margins{Left: 5, Top: 5, Right: 5, Bottom: 5}},
			MaxSize: Size{Width: 100, Height: 140},
			Background: SolidColorBrush{Color: bgColor},
			OnMouseDown: func(x, y int, button walk.MouseButton) {
				app.selectCoverImage(name)
				app.updateCoverSelectionUI(idx)
			},
			Children: []Widget{
				ImageView{
					Image: fullPath,
					Mode: ImageViewModeZoom,
					MinSize: Size{Width: 90, Height: 120},
					MaxSize: Size{Width: 90, Height: 120},
					OnMouseDown: func(x, y int, button walk.MouseButton) {
						app.selectCoverImage(name)
						app.updateCoverSelectionUI(idx)
					},
				},
			},
		})
	}
	
	defaultContent := "1. 全文9900+字，已完结\r\n2. 下单秒发货，默认链接\r\n3. 提取链接：对话框内、物流信息处\r\n4. 电子书籍，下单后恕不退换"

	builder := NewBuilder(app.ContentComposite)
	
	err = Composite{
		AssignTo: &app.CoverComposite,
		Layout:   HBox{Margins: Margins{Left: 10, Top: 10, Right: 10, Bottom: 10}},
		Children: []Widget{
			// Left Panel (Input & Preview)
			Composite{
				Layout: VBox{MarginsZero: true},
				Children: []Widget{
					// Block 1: Image Selection
					Label{Text: "选择图像 (点击选中):"},
					ScrollView{
						MaxSize: Size{Height: 160},
						Layout:  Flow{Margins: Margins{Left: 5, Top: 5, Right: 5, Bottom: 5}, Spacing: 10},
						Children: thumbWidgets,
					},
					
					// Block 2: Title Input
					Composite{
						Layout: HBox{MarginsZero: true},
						Children: []Widget{
							Label{Text: "标题:"},
							LineEdit{
								AssignTo: &app.CoverTitleInput,
								Text:     "看文须知",
							},
							Label{Text: "字号:"},
							LineEdit{
								AssignTo: &app.CoverTitleSizeInput,
								Text:     "60",
								MaxSize:  Size{Width: 40},
							},
						},
					},
					
					// Block 3: Content Input
					Composite{
						Layout: HBox{MarginsZero: true},
						Children: []Widget{
							Label{Text: "内容:"},
							HSpacer{},
							Label{Text: "字号:"},
							LineEdit{
								AssignTo: &app.CoverContentSizeInput,
								Text:     "40",
								MaxSize:  Size{Width: 40},
							},
						},
					},
					TextEdit{
						AssignTo: &app.CoverContentInput,
						Text:     defaultContent,
						MinSize:  Size{Height: 100},
					},
					
					// Block 4: Processed Image Display
					VSpacer{Size: 10},
					Label{Text: "预览:"},
					ImageView{
						AssignTo: &app.CoverImageView,
						Mode:     ImageViewModeZoom,
						MinSize:  Size{Width: 300, Height: 400}, 
					},
				},
			},
			
			// Right Panel (Buttons)
			Composite{
				Layout:  VBox{Margins: Margins{Left: 10}},
				MaxSize: Size{Width: 150},
				Children: []Widget{
					PushButton{
						Text:      "生成",
						OnClicked: app.handleCoverGenerate,
					},
					PushButton{
						Text:      "复制",
						OnClicked: app.handleCoverCopy,
					},
					VSpacer{},
				},
			},
		},
	}.Create(builder)
	
	if err != nil {
		fmt.Println("Error creating cover view:", err)
	}
}

func (app *NovelApp) selectCoverImage(name string) {
	app.CoverSelectedImage = name
	
	// Need to find the index of this name in the image list to update the corresponding composite
	// But we don't store the image list in app struct.
	// We can store the image names in the app struct or just rely on the order if we don't change it.
	// A better way: The closure for OnMouseDown already knows the index if we capture it.
	// So let's pass index to selectCoverImage or handle it in the closure.
}

func (app *NovelApp) updateCoverSelectionUI(selectedIndex int) {
	for i, cmp := range app.CoverThumbComposites {
		if cmp == nil { continue }
		
		if i == selectedIndex {
			// Selected: Blue border/background
			b, _ := walk.NewSolidColorBrush(walk.RGB(173, 216, 230)) // Light Blue
			cmp.SetBackground(b)
		} else {
			// Unselected: Default
			b, _ := walk.NewSolidColorBrush(walk.RGB(240, 240, 240))
			cmp.SetBackground(b)
		}
	}
}

func (app *NovelApp) handleCoverGenerate() {
	if app.CoverTitleInput == nil || app.CoverContentInput == nil {
		return
	}
	
	// Get inputs
	imageName := app.CoverSelectedImage
	if imageName == "" {
		walk.MsgBox(app.MainWindow, "错误", "请选择图片", walk.MsgBoxIconError)
		return
	}
	
	basePath := filepath.Join("e:\\worksapce\\short_stories\\novel_reader\\首图", imageName)
	
	// If relative path exists, use it
	if _, err := os.Stat(filepath.Join("首图", imageName)); err == nil {
		basePath = filepath.Join("首图", imageName)
	}
	
	title := app.CoverTitleInput.Text()
	content := app.CoverContentInput.Text()
	
	// Parse font sizes
	titleSize, err := strconv.ParseFloat(app.CoverTitleSizeInput.Text(), 64)
	if err != nil || titleSize <= 0 {
		titleSize = 60
	}
	
	contentSize, err := strconv.ParseFloat(app.CoverContentSizeInput.Text(), 64)
	if err != nil || contentSize <= 0 {
		contentSize = 40
	}
	
	// Generate
	gen := novel.NewCoverGenerator(app.Processor.FontPath)
	img, err := gen.GenerateCover(basePath, title, content, titleSize, contentSize)
	if err != nil {
		walk.MsgBox(app.MainWindow, "错误", "生成失败: "+err.Error(), walk.MsgBoxIconError)
		return
	}
	
	// Display
	bitmap, err := walk.NewBitmapFromImage(img)
	if err != nil {
		fmt.Println("Error creating bitmap:", err)
		return
	}
	app.CoverImageView.SetImage(bitmap)
	
	// Store image for copying
	app.LastCoverImage = img
}

func (app *NovelApp) handleCoverCopy() {
	if app.LastCoverImage == nil {
		walk.MsgBox(app.MainWindow, "错误", "请先生成图片", walk.MsgBoxIconError)
		return
	}
	
	// Save to temp file to copy to clipboard (PowerShell method requires file)
	// Or use a clipboard library. Since we used PowerShell before, let's stick to it but use a temp file.
	tempDir := os.TempDir()
	tempFile := filepath.Join(tempDir, "novel_reader_cover_temp.png")
	
	// Save image to temp file
	f, err := os.Create(tempFile)
	if err != nil {
		walk.MsgBox(app.MainWindow, "错误", "无法创建临时文件: "+err.Error(), walk.MsgBoxIconError)
		return
	}
	defer f.Close()
	
	if err := png.Encode(f, app.LastCoverImage); err != nil {
		walk.MsgBox(app.MainWindow, "错误", "无法保存临时图片: "+err.Error(), walk.MsgBoxIconError)
		return
	}
	f.Close() // Close before using in PowerShell
	
	path := strings.ReplaceAll(tempFile, "'", "''")
	
	// Use PowerShell to copy image to clipboard
	cmd := exec.Command("powershell", "-WindowStyle", "Hidden", "-Command", "Add-Type -AssemblyName System.Windows.Forms; $img = [System.Drawing.Image]::FromFile('"+path+"'); [System.Windows.Forms.Clipboard]::SetImage($img); $img.Dispose()")
	
	if err := cmd.Run(); err != nil {
		walk.MsgBox(app.MainWindow, "错误", "复制失败: "+err.Error(), walk.MsgBoxIconError)
	} else {
		walk.MsgBox(app.MainWindow, "成功", "图片已复制到剪贴板", walk.MsgBoxIconInformation)
	}
}
