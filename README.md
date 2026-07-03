# 高中化学知识指南

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

## 更新数据

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