# Novel Reader Application

This is a Windows desktop application for reading novels, designed with a "Phone View" experience.
Built with Go and Walk (Windows App Library Kit).

## Features
- **Novel Reading**: Import from File or URL.
- **Phone Simulation**: Reading area simulates 1080x1440 resolution.
- **Export/Screenshot**: Generate JPG images of pages with text typeset on the background.
- **Edit & Save**: Edit content and save back to local file.
- **Background**: Customizable background image.

## Requirements
- **Windows** (Tested on Windows 10/11)
- **Fonts**: The application looks for `C:\Windows\Fonts\simhei.ttf` (SimHei) for rendering Chinese characters in exports. If not found, it tries `arial.ttf`.
  - *Note*: If Chinese characters appear as boxes in the exported images, please ensure `simhei.ttf` exists or update the font path in the code.

## Usage
1. Run `novel_reader.exe`.
2. Click "Novel Reading" (小说阅读) in the sidebar.
3. Click "Import" (导入) to load a novel.
   - **URL**: Enter a URL (content will be downloaded).
   - **File**: Select a local `.txt` file.
4. Use "Previous" (上一页) and "Next" (下一页) to navigate.
5. Click "Screenshot" (截图) to export the first N pages as images.
   - Images are saved in a folder named after the novel title.
6. Click "Edit" (编辑) to modify text. Click "Save" (保存) to apply changes and save to file.

## Build
To rebuild the application (Requires Go installed):

**Standard Build:**
```bash
go mod tidy
go build -o novel_reader.exe
```

**Optimized Build (Smaller size, no console window):**
```bash
go mod tidy
go build -ldflags "-s -w -H windowsgui" -o novel_reader.exe
```
* `-s -w`: Strip debug information and symbol table to reduce file size.
* `-H windowsgui`: Hide the command prompt window when running the application.

## Note
- The `novel_reader.exe.manifest` file enables modern Windows visual styles. Keep it in the same directory as the executable.
