# LINE Local MCP

[![Tests](https://github.com/curzer1995-777/line-local-mcp/actions/workflows/tests.yml/badge.svg)](https://github.com/curzer1995-777/line-local-mcp/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB.svg)](https://www.python.org/)

[繁體中文](#繁體中文) · [English](#english)

> **Beta / macOS only / unofficial project.** This project is not affiliated with, endorsed by, or sponsored by LY Corporation or LINE. It accesses private, undocumented local storage that may change without notice.

## 繁體中文

LINE Local MCP 是一個唯讀的 [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server，讓支援 MCP 的 AI 可以快速搜尋使用者自己 Mac 上的 LINE Desktop 對話紀錄，包括自己傳出與對方傳入的訊息。

它不需要 LINE 官方帳號、不需要把親友拉進群組，也不會逐一點開聊天室。它只讀取 LINE Desktop 已同步到本機的資料庫快照，不會發訊息、修改未讀狀態或寫回 LINE。

### 專案起源

這個專案源自一個很日常的需求：希望每天的 AI brief 能涵蓋 LINE 裡真正需要回覆的工作與私人訊息，但又不想為了自動化申請 LINE 官方帳號、建立額外群組，或讓程式慢慢點開每一個聊天室。

最初評估過 GUI 自動化，但大量對話會很慢，也可能影響畫面與未讀狀態；只讀取通知則又只能看到對方說了什麼，缺少自己回覆的上下文。最後採用本機唯讀資料庫快照，讓 AI 能在幾秒內讀取完整雙向上下文，同時把「讀取」與「回覆／發送」明確分開。

### 工作場景：LINE 作為長期工作入口，跨來源辨識任務

對長期在工作環境使用 LINE 的人來說，一個任務可能從 LINE 的客戶訊息開始，接著在 Slack 裡由同事補充背景，Gmail 裡留有報價或需求文件，最後再由行事曆上的會議決定期限。若只看單一聊天室，AI 很容易把「已完成」、「等待他人確認」與「尚未回覆」混在一起。

在使用者已授權的前提下，可以把本專案當成 LINE 的唯讀上下文入口，再搭配其他具備唯讀權限的 AI service／connector 讀取：

- LINE 對話：辨識對方的請求、自己是否已回覆，以及對話中的承諾與期限。
- Slack 頻道與 thread：補充內部討論、負責人、決策與目前阻塞點。
- Gmail 郵件與 thread：找出正式需求、附件線索、客戶回覆與待確認事項。
- 行事曆事件：對照會議、預定交付時間與已經排入時段的工作。

AI 可以將相同主題的訊息交叉比對後，產出一份工作 brief，例如：

1. 找出「需要我處理」的任務，依期限、重要性與是否阻塞他人排序。
2. 將 LINE 的外部請求與 Slack／Gmail 的內部佐證連在一起，避免重複列出同一件事。
3. 清楚區分「已完成」、「已有回覆但尚未確認」、「承諾過但缺少完成證據」與「待回覆」。
4. 為每項任務附上來源、目前狀態、下一步與不確定性；找不到期限或負責人時保留為「未知」，不自行補值。
5. 只提出草稿或提醒，將回覆 LINE、寄信、發 Slack 訊息或修改行事曆保留給使用者核准。

例如，客戶在 LINE 詢問進度、同事在 Slack 說明還在等資料、Gmail 有最新需求版本，而行事曆顯示明天有客戶會議時，AI brief 應該整理成「客戶進度回覆｜明日會議前確認｜目前等待內部資料｜來源：LINE／Slack／Gmail／Calendar」，而不是直接判定為已完成或代替使用者送出訊息。這個場景適合做成每日早上、會議前或每週回顧的 read-only brief。

本專案本身仍只負責讀取 LINE；Slack、Gmail、行事曆與 AI service 的連接方式、權限與保存政策由各自的 connector／AI client 管理。所有跨來源內容都可能進入 AI context，使用前應確認使用者的存取權限、公司政策與服務的隱私／保存設定。

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

### 參與開源專案

- 提交問題或功能建議：[GitHub Issues](https://github.com/curzer1995-777/line-local-mcp/issues)
- 貢獻程式碼：[CONTRIBUTING.md](CONTRIBUTING.md)
- 支援範圍：[SUPPORT.md](SUPPORT.md)
- 安全通報：[SECURITY.md](SECURITY.md)
- 專案治理：[GOVERNANCE.md](GOVERNANCE.md)
- 版本變更：[CHANGELOG.md](CHANGELOG.md)
- 社群行為準則：[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)

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

### Workplace scenario: LINE as a long-term task inbox

For people who use LINE throughout the workday, one task may start in a customer chat, gain internal context in a Slack channel or thread, receive a formal requirement in Gmail, and acquire a deadline through a calendar event. Looking at only one chat makes it easy to confuse completed work with an unanswered request or a promise that still lacks completion evidence.

With the user's authorization, this project can provide LINE's read-only context alongside other read-only AI services or connectors for:

- LINE conversations: requests, replies, commitments, and stated deadlines.
- Slack channels and threads: internal decisions, owners, dependencies, and blockers.
- Gmail threads: formal requirements, customer replies, and document or attachment clues.
- Calendar events: meetings, scheduled delivery times, and reserved work blocks.

An AI client can correlate the same topic across these sources and produce a brief that identifies tasks requiring the user's attention, links external requests to internal evidence, separates completed items from pending confirmation or unanswered requests, and shows the source, status, next action, and uncertainty for each item. Missing owners or deadlines should remain unknown rather than being inferred. The client can prepare a draft or reminder, while sending a LINE reply, email, Slack message, or calendar change remains a separate user-approved action.

For example, if a customer asks for an update in LINE, a teammate says in Slack that data is still pending, Gmail contains the latest requirements, and a customer meeting is scheduled for tomorrow, the brief should say that the update needs confirmation before tomorrow's meeting and cite those sources. It should not mark the task complete or send a message on the user's behalf. This makes the scenario suitable for a morning brief, meeting-prep brief, or weekly review.

This project still only reads LINE. The connection method, permissions, retention, and privacy policy for Slack, Gmail, Calendar, and the AI service belong to their respective connectors or clients. Treat all cross-source content as potentially entering the AI context and verify access rights and organizational policy before use.

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

### Open source community

Issues and contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md), [SUPPORT.md](SUPPORT.md), [GOVERNANCE.md](GOVERNANCE.md), [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md), and [CHANGELOG.md](CHANGELOG.md).

## License

MIT. See [LICENSE](LICENSE).
