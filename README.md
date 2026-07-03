# 高中化学知识点 · 静态站点

纯静态页面，浏览器直接解析 `data/` 下的 JSONL 并展示，可直接部署到 GitHub Pages。

## 目录

```
pages/
  index.html              前端（静态，运行时 fetch JSONL）
  .nojekyll               关闭 Jekyll，保证文件原样发布
  data/
    manifest.json         教材清单（静态站点无法列目录，用它列出书单）
    explicit/*.jsonl      各教材显式知识点 (kp-explicit-ai-v1)
    teaching/*.jsonl      各教材教学辅助数据 (kp-teaching-v1)
```

## 更新数据（只改数据、不改前端）

在项目根目录重新生成 JSONL 后，重跑：

```bash
python3 scripts/build_pages.py --clean
```

它会把最新的 JSONL 拷进 `pages/data/` 并重建 `manifest.json`。前端无需改动。

## 本地预览

```bash
python3 -m http.server -d pages 8000
# 打开 http://127.0.0.1:8000
```

（或在项目根用 `python3 scripts/serve_kp.py` 预览实时数据，无需先 build。）

## 部署到 GitHub Pages

任选一种：

- **docs 目录方式**：把本目录改名/复制为仓库根的 `docs/`，push 后在
  Settings → Pages → Source 选 `main` 分支 `/docs`。
- **gh-pages 分支方式**：把 `pages/` 内容 push 到 `gh-pages` 分支根目录，
  Settings → Pages 选该分支。

因为用的是相对路径 `data/...`，部署在 `https://<user>.github.io/<repo>/` 这类
子路径下也能正常工作。
