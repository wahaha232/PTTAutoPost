# 第三方元件與授權聲明

本文件列出 PTT AutoPost 發行版所含主要第三方元件。完整授權全文放在 `licenses/`，
本程式不會修改這些元件。

| 元件 | 版本（本次建置） | 授權 | 用途 |
|---|---|---|---|
| PySide6（Qt for Python） | 6.11.2 | LGPL-3.0-only（亦可依 GPL 或商業授權） | 圖形介面、網路、WebSocket |
| Qt | 6.11.2 | LGPL-3.0-only（亦可依 GPL 或商業授權） | PySide6 使用的函式庫與外掛 |
| shiboken6 | 6.11.2 | LGPL-3.0-only | PySide6 繫結 |
| requests | 2.34.2 | Apache-2.0 | HTTP 擷取 |
| beautifulsoup4 | 4.15.0 | MIT | HTML 解析 |
| lxml | 6.1.1 | BSD-3-Clause | HTML／XML 解析 |
| charset-normalizer | 3.4.9 | MIT | 編碼偵測 |
| Python | 3.12 | PSF License 2.0 | 執行環境 |
| PyInstaller | 6.22.2 | GPL-2.0-or-later，含 bootloader exception | 打包工具（bootloader 隨執行檔散布） |

## Qt／PySide6（LGPL-3.0）說明

- 本程式以 **onedir（資料夾版）** 發行，Qt 與 PySide6 的 DLL 是資料夾內的獨立檔案，
  使用者可以用介面相容的版本替換它們，不需要修改或重新編譯本程式。
- 本程式未修改 Qt／PySide6。對應原始碼可從下列位置取得：
  - Qt：<https://code.qt.io/cgit/qt/>
  - PySide6：<https://code.qt.io/cgit/pyside/pyside-setup.git/>
  - PyPI 原始碼套件：<https://pypi.org/project/PySide6/>
- LGPL-3.0 全文：`licenses/LGPL-3.0.txt`；GPL-3.0 全文：`licenses/GPL-3.0.txt`。
- 若您散布本程式，請一併保留本文件、`LICENSE` 與 `licenses/` 資料夾，並自行確認
  符合 LGPL 的相關義務。

## 其他元件的授權全文

- requests（Apache-2.0）：`licenses/requests-Apache-2.0.txt`
- beautifulsoup4（MIT）：`licenses/beautifulsoup4-MIT.txt`
- charset-normalizer（MIT）：`licenses/charset-normalizer-MIT.txt`
- lxml（BSD-3-Clause）：`licenses/lxml-BSD-3-Clause.txt`
- lxml 內附程式庫：`licenses/lxml-bundled-libraries.txt`
- Python 3.12：`licenses/Python-3.12-PSF.txt`
- PyInstaller（含 bootloader exception）：`licenses/PyInstaller-GPL-2.0-with-exception.txt`

## 注意

本文件為工程整理，**不構成法律建議**。公開發佈前請依實際散布方式（例如是否收費、
是否提供原始碼、是否修改 Qt）諮詢專業人士，確認授權義務。
