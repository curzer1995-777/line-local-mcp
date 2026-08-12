# LINE Local MCP

[繁體中文](#繁體中文) · [English](#english)

> **Beta / macOS only / unofficial project.** This project is not affiliated with, endorsed by, or sponsored by LY Corporation or LINE. It accesses private, undocumented local storage that may change without notice.

## 繁體中文

LINE Local MCP 是一個唯讀的 [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server，讓支援 MCP 的 AI 可以快速搜尋使用者自己 Mac 上的 LINE Desktop 對話紀錄，包括自己傳出與對方傳入的訊息。

它不需要 LINE 官方帳號、不需要把親友拉進群組，也不會逐一點開聊天室。它只讀取 LINE Desktop 已同步到本機的資料庫快照，不會發訊息、修改未讀狀態或寫回 LINE。

### 專案起源

這個專案源自一個很日常的需求：希望每天的 AI brief 能涵蓋 LINE 裡真正需要回覆的工作與私人訊息，但又不想為了自動化申請 LINE 官方帳號、建立額外群組，或讓程式慢慢點開每一個聊天室。

最初評估過 GUI 自動化，但大量對話會很慢，也可能影響畫面與未讀狀態；只讀取通知則又只能看到對方說了什麼，缺少自己回覆的上下文。最後採用本機唯讀資料庫快照，讓 AI 能在幾秒內讀取完整雙向上下文，同時把「讀取」與「回覆／發送」明確分開。

### 能做什麼

提供 5 個唯讀工具，AI 可依使用者指令自行組合：

| 工具 | 用途 |
| --- | --- |
| `line_status` | 檢查本機 LINE 資料是否可讀及同步時間 |
| `list_chats` | 列出最近或未讀聊天室，取得穩定的 chat ID |
| `get_messages` | 讀取單一聊天室的雙向訊息 |
| `search_messages` | 搜尋自己傳出與收到的文字訊息 |
| `get_recent_activity` | 批次取得最近活動，用於每日／每週 brief |

LINE 官方／商業帳號預設排除；可由呼叫端明確要求納入。密碼、驗證碼及 URL 中常見的 token 參數預設遮蔽。

### 使用前提

- macOS（目前唯一支援的平台）。
- [LINE Desktop](https://line.me/) 已安裝在 `/Applications/LINE.app` 並登入。
- Python 3.11 以上。
- Apple Command Line Tools，提供 `codesign` 與 `lldb`。可用 `xcode-select --install` 安裝。
- 啟動 MCP 的 Terminal 或 AI client 具備 macOS「完整磁碟存取」。
- 只用於使用者本人有權存取的 LINE 帳號與裝置。
- 使用雲端 AI 時，Mac 必須保持醒著，LINE 必須已同步；Mac 睡眠時不會產生更新資料。

目前已在 Apple Silicon Mac、LINE Desktop 9.13.0、macOS 26.5.1 上完成端到端驗證。其他 LINE／macOS 版本可能可用，但尚未保證。

### 安裝

1. 下載或 clone 此 repo。
2. 在 Finder 雙擊 `install.command`；若 macOS 阻擋，請按右鍵選擇「打開」。
3. 安裝程式會建立此資料夾專用的 `.venv`，安裝相依套件並執行 readiness check。
4. 如果尚未有資料庫金鑰，安裝程式會引導一次性設定：
   - 建立 LINE app 的臨時副本；
   - 請使用者在臨時副本登入同一個 LINE 帳號；
   - 只對臨時副本使用 Apple `lldb` 讀取記憶體；
   - 每個候選金鑰都必須成功解開使用者的本機資料庫才會被接受；
   - 經驗證的金鑰只存進 macOS Keychain，不會顯示或寫入 repo；
   - 臨時 app 與驗證用快照會在流程結束後刪除。

可以隨時檢查：

```bash
.venv/bin/line-local-mcp --doctor
```

輸出只包含連線狀態、對話／訊息筆數與同步時間，不會列出訊息內容。

### 接到 AI client

安裝後的固定指令是：

```text
/完整路徑/line-local-mcp/.venv/bin/line-local-mcp
```

通用 STDIO MCP 設定：

```json
{
  "mcpServers": {
    "line": {
      "command": "/完整路徑/line-local-mcp/.venv/bin/line-local-mcp"
    }
  }
}
```

Codex CLI：

```bash
codex mcp add line -- /完整路徑/line-local-mcp/.venv/bin/line-local-mcp
```

依 [OpenAI MCP 文件](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)，新增後重啟桌面 app／client，再用 `/mcp` 確認 `line` 已連線。

可以這樣要求 AI：

- 「讀我過去 24 小時的 LINE，排除官方帳號，整理待回覆事項。」
- 「搜尋最近一週提到『發票』的 LINE 訊息，依聊天室整理。」

### 雲端 AI 與 tunnel

本機 HTTP 模式只監聽 loopback：

```bash
.venv/bin/line-local-mcp --transport streamable-http --port 8765
```

端點為 `http://127.0.0.1:8765/mcp`。它沒有內建公開網路驗證，**請勿直接 port-forward 或暴露到公網**。

OpenAI 產品可使用官方 [Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)，透過 outbound HTTPS 連接本機 STDIO 或 loopback HTTP server。無論使用哪種 tunnel，Mac、LINE 和 tunnel client 都必須保持運作。

### 安全性與隱私

請在使用前理解以下邊界：

- **唯讀保證範圍：**所有 MCP tools 都標記為 read-only；程式只開啟複製到暫存目錄的資料庫快照，不提供傳送、刪除、已讀或修改訊息的工具。
- **一次性 debugger 設定：**為取得 LINE 私有資料庫的解密金鑰，設定流程會重新簽署並啟動一份臨時 LINE 副本，再使用 `lldb` 讀取該副本的記憶體。它不會 attach 原始 `/Applications/LINE.app`。
- **金鑰保存：**只有成功驗證的金鑰會存入 macOS Keychain 的 `line-cua-mcp-dbkey`；MCP 回傳值、日誌及 repo 都不包含金鑰。
- **訊息會進入 AI context：**MCP 本身在本機讀取資料，但被工具回傳的訊息會送到呼叫它的 AI client／模型。請先確認該服務的隱私、保存與訓練政策。
- **遮蔽不是 DLP：**內建遮蔽只涵蓋常見密碼標籤、驗證碼和敏感 URL query keys，不保證辨識所有個資、金鑰、銀行資料或公司機密。
- **完整磁碟存取：**macOS 權限會讓啟動程式具備廣泛的本機讀取能力。只授權你信任的 Terminal／AI client，並檢查其自身安全性。
- **私有格式：**LINE 更新可能改變資料庫格式、路徑或加密方式。更新後先執行 `--doctor`。

更多威脅模型、回報方式與維護政策請見 [SECURITY.md](SECURITY.md)。

### 設定

| 環境變數 | 說明 |
| --- | --- |
| `LINE_MCP_DB_PATH` | 指定資料庫檔案；多帳號時使用 |
| `LINE_MCP_KEYCHAIN_SERVICE` | 更改 Keychain service 名稱 |
| `LINE_MCP_REDACT_SENSITIVE=false` | 關閉敏感字串遮蔽；不建議 |
| `LINE_MCP_APP_PATH` | 一次性設定使用的 LINE app 路徑 |

若 LINE 更新後金鑰失效：

```bash
.venv/bin/line-local-mcp --setup-key
```

### 疑難排解

**找不到 LINE database**

- 確認 LINE Desktop 已登入並完成同步。
- 對 Terminal 或 AI client 開啟「系統設定 → 隱私權與安全性 → 完整磁碟存取」，再完整重啟該程式。

**Keychain key unavailable / file is not a database**

- 執行 `.venv/bin/line-local-mcp --setup-key`，並確定臨時 LINE 副本登入的是同一帳號。

**AI 找不到新 MCP**

- 檢查設定中的 command 是絕對路徑。
- 執行 `.venv/bin/line-local-mcp --doctor`。
- 重啟 AI client；Codex 可用 `codex mcp list` 檢查。

**訊息不是最新的**

- MCP 只讀取 LINE Desktop 已同步到 Mac 的資料；喚醒 Mac、開啟 LINE 並等待同步。

### 開發與測試

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/pytest
```

測試使用合成資料，不需要真實 LINE 對話或金鑰。貢獻方式請見 [CONTRIBUTING.md](CONTRIBUTING.md)。

### 限制與免責

- Beta：目前只對一組 macOS／LINE Desktop 環境完成真實端到端驗證。
- 只讀本機已同步的文字與部分非文字預覽；不下載附件內容。
- LINE 的私有格式或服務條款可能變更；使用者須自行確認所在地法律、帳號權限與 LINE 條款。
- 僅供使用者存取本人有權使用的帳號與資料，請勿用於未經授權的監控、存取或金鑰擷取。
- LINE 及其商標屬其各自權利人。本專案與 LY Corporation／LINE 無關，未獲其背書。

---

## English

LINE Local MCP is a read-only Model Context Protocol server for searching both sides of a user's own LINE Desktop history on macOS. It reads disposable snapshots of the local encrypted database; it does not click chats, change unread state, send messages, or require a LINE Official Account.

### Why this project exists

The project began with a practical daily-brief problem: relevant work and personal follow-ups often live in LINE, but creating an Official Account, adding family or friends to bot groups, or clicking through every chat is intrusive and slow. Notifications only show the other person's messages and omit the user's replies. A local read-only snapshot provides fast, bidirectional context while keeping reading strictly separate from sending.

### Requirements

- macOS and LINE Desktop installed at `/Applications/LINE.app`, signed in and synchronized.
- Python 3.11+ and Apple Command Line Tools (`xcode-select --install`).
- Full Disk Access for the Terminal or AI client that launches the MCP server.
- Use only with a LINE account and Mac the user is authorized to access.

The current end-to-end test baseline is Apple Silicon, LINE Desktop 9.13.0, and macOS 26.5.1. Other versions are not yet guaranteed.

### Quick start

1. Clone or download this repository.
2. Double-click `install.command` (right-click → Open if macOS blocks it).
3. Follow the one-time temporary-LINE-copy setup if prompted.
4. Add the absolute `.venv/bin/line-local-mcp` command to a local STDIO MCP client.
5. Restart the client and verify the `line` server.

Codex example:

```bash
codex mcp add line -- /absolute/path/line-local-mcp/.venv/bin/line-local-mcp
```

Read the Traditional Chinese sections above for the complete setup, security model, cloud tunnel guidance, troubleshooting, and limitations. Security reports should follow [SECURITY.md](SECURITY.md).

## License

MIT. See [LICENSE](LICENSE).
