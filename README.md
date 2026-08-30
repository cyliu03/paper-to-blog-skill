# paper-to-blog

`paper-to-blog` 是一个面向计算机科学、人工智能和脑机接口论文的 Codex Skill。它把论文整理为可追溯的中文精读博客档案，并在明确调用时通过已登录浏览器保存为 CSDN 草稿；如果配置了 WordPress.com，也会创建长期存档草稿。

它最重要的约束是：博客中的图片只能来自论文正文或补充材料。允许完整提取原图和忠实裁剪子图，但不生成、重绘、修复或装饰图片。

## 功能

- 接受本地 PDF、PDF 链接、DOI、arXiv、OpenReview 和出版社页面。
- 生成通常 4,000–6,000 字的中文精读博客。
- 渲染全部页面并登记论文原图的图号、页码、图注、来源和哈希。
- 输出 Markdown、HTML、PDF、图片、元数据、预览报告和发布状态。
- 在上传前执行来源与内容一致性检查，发现无来源图片时拒绝继续。
- 通过 WordPress.com 官方接口创建或更新草稿。
- 通过可见浏览器界面填写、保存并核验 CSDN 草稿；不调用非公开接口。
- 重复执行时恢复失败步骤并优先更新现有草稿，避免重复文章。

## 工作模式

| 调用方式 | 默认结果 |
| --- | --- |
| 明确调用 `$paper-to-blog 精读 <论文>` | 本地完整档案 + 已保存并核验的 CSDN 草稿 |
| `$paper-to-blog 仅生成预览 <论文>` | 仅生成本地档案 |
| 普通自然语言论文阅读请求触发 Skill | 仅生成本地档案 |
| `$paper-to-blog 确认上传草稿 <bundle>` | 校验既有档案并上传或更新草稿 |

无论哪种模式，Skill 都不会公开发布文章。

## 安装

需要 Python 3.10 或更高版本。

```bash
git clone https://github.com/cyliu03/paper-to-blog-skill.git
cd paper-to-blog-skill
python -m pip install -r requirements.txt
```

### Codex 个人 Skill

把仓库中的 `paper-to-blog/` 目录完整复制到：

```text
$CODEX_HOME/skills/paper-to-blog/
```

重新打开 Codex 后即可调用 `$paper-to-blog`。不要只复制 `SKILL.md`，脚本、参考文档、模板和测试文件都属于 Skill 的一部分。

### GitHub Copilot 项目 Skill

把 `paper-to-blog/` 目录完整复制到目标项目的：

```text
.github/skills/paper-to-blog/
```

浏览器草稿上传依赖宿主代理提供可控制且已登录的浏览器。若环境不具备该能力，Skill 会保留已通过校验的本地档案并停止在上传步骤。

## 使用

```text
$paper-to-blog 精读 E:\papers\example.pdf
$paper-to-blog 精读 https://arxiv.org/abs/2501.00001
$paper-to-blog 仅生成预览 10.0000/example-doi
$paper-to-blog 确认上传草稿 E:\paper_reader\articles\2026-08-30-example
```

文章默认写入用户指定的位置；没有指定时，依次使用 `PAPER_BLOG_ROOT` 和当前工作区下的 `articles/`。

## WordPress.com 配置

WordPress 适配器只读取以下环境变量：

```text
PAPER_BLOG_WP_SITE
PAPER_BLOG_WP_TOKEN
```

令牌不得写入仓库、文章目录、日志或聊天内容。未配置 WordPress 时，本地档案和 CSDN 草稿流程仍可继续。

## 本地档案

每篇论文生成一个独立目录：

```text
YYYY-MM-DD-paper-slug/
├── article.md
├── article.html
├── preview.md
├── manifest.json
├── publication.json
├── source/
└── figures/
```

`manifest.json` 是论文与图片溯源记录，`publication.json` 只保存草稿 ID、编辑地址、状态和内容哈希，不保存凭据。

## 验证

```bash
python paper-to-blog/scripts/run_tests.py
```

测试覆盖 PDF 预处理、DOI 解析、内网 URL 拒绝、图像溯源、未登记图片拒绝、WordPress 草稿创建、幂等更新和缺失配置等场景。

## 安全与版权边界

- 不绕过付费墙或访问控制；无法合法获得全文时要求用户提供 PDF。
- 原论文 PDF 只保存在本地，不上传到博客平台。
- 不读取或导出 Cookie、密码、浏览器存储及会话凭据。
- CSDN 仅使用可见编辑器，且只保存草稿。
- 使用论文图片时仍应遵守原论文许可证、合理使用规则和平台要求。

## 设计依据

仓库结构遵循 Codex Skill 的渐进式披露原则：`SKILL.md` 负责触发与路由，`references/` 保存细节，`scripts/` 承担可重复且需要严格校验的操作，`tests/` 提供失败即停止的质量门。设计时参考了 [OpenAI Skills](https://github.com/openai/skills)、[Anthropic Skills](https://github.com/anthropics/skills)、[GitHub Awesome Copilot Skills](https://github.com/github/awesome-copilot/tree/main/skills) 和 [GitHub Agent Skills 文档](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/add-skills)。

## 许可证

[MIT License](LICENSE)
