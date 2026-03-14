package ui

import (
	"fmt"
	"strconv"
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
	
	// State
	IsEditing bool
}

func NewNovelApp() *NovelApp {
	processor := novel.NewNovelProcessor()
	
	// Try to load font
	fonts := []string{
		"C:\\Windows\\Fonts\\simhei.ttf",
		"C:\\Windows\\Fonts\\msyh.ttc",
		"C:\\Windows\\Fonts\\msyh.ttf",
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
	if _, err := (MainWindow{
		AssignTo: &app.MainWindow, // Assign directly to prevent nil panic in handlers
		Title:    "Novel Reader",
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
}

func (app *NovelApp) showNovelView() {
	if app.NovelComposite == nil {
		app.createNovelView()
	} else {
		app.NovelComposite.SetVisible(true)
	}
	app.updateReadingView()
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
						MinSize:  Size{Width: 400, Height: 600}, 
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

	var dlg *walk.Dialog
	var urlTE *walk.TextEdit
	var titleTE *walk.TextEdit
	
	Dialog{
		AssignTo: &dlg,
		Title:    "导入小说",
		MinSize:  Size{Width: 500, Height: 350},
		Layout:   VBox{},
		Children: []Widget{
			Label{Text: "小说标题 (必填):"},
			TextEdit{AssignTo: &titleTE},
			VSpacer{Size: 10},
			PushButton{
				Text: "从文件导入",
				OnClicked: func() {
					if titleTE.Text() == "" {
						walk.MsgBox(dlg, "错误", "标题不能为空", walk.MsgBoxIconError)
						return
					}
					
					dlg.Close(walk.DlgCmdOK) 
					dlgFile := new(walk.FileDialog)
					dlgFile.Filter = "Text Files (*.txt)|*.txt|All Files (*.*)|*.*"
					if ok, err := dlgFile.ShowOpen(app.MainWindow); err != nil {
						return
					} else if ok {
						app.Processor.Title = titleTE.Text()
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
				VScroll:  true, // Enable vertical scroll
				MinSize:  Size{Height: 100},
			},
			Composite{
				Layout: HBox{},
				Children: []Widget{
					PushButton{
						Text: "从剪贴板粘贴",
						OnClicked: func() {
							if text, err := walk.Clipboard().Text(); err == nil {
								urlTE.SetText(text)
							}
						},
					},
					HSpacer{},
					PushButton{
						Text: "从链接导入",
						OnClicked: func() {
							if titleTE.Text() == "" {
								walk.MsgBox(dlg, "错误", "标题不能为空", walk.MsgBoxIconError)
								return
							}
							
							url := urlTE.Text()
							if url != "" {
								dlg.Close(walk.DlgCmdOK)
								app.Processor.Title = titleTE.Text()
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
