import os
import re
import json
import frontmatter
import bibtexparser
from pathlib import Path
from PIL import Image, ImageOps

# 路径配置 (依据脚本当前所在位置推导根目录)
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
REPO_PATH = ROOT_DIR / "obsidian-backup"
PAPERS_DIR = REPO_PATH / "PaperNote" / "papers"
PIC_SRC_DIR = REPO_PATH / "PaperNote" / "_img"
PIC_DEST_DIR = ROOT_DIR / ".img"
README_PATH = ROOT_DIR / "README.md"
JSON_OUTPUT = ROOT_DIR / "extracted_papers.json"

print("SCRIPT_DIR: ", SCRIPT_DIR)
print("ROOT_DIR: ", ROOT_DIR)


def clean_bibtex_string(s):
    """去除 bibtex 中常见的花括号"""
    return s.replace('{', '').replace('}', '').replace('\n', ' ').strip()


def parse_bibtex(bibtex_str):
    if not bibtex_str.strip():
        return {}
    try:
        bib_database = bibtexparser.loads(bibtex_str)
        if not bib_database.entries:
            return {}
        entry = bib_database.entries[0]

        raw_doi = entry.get('doi', '')
        raw_url = entry.get('url', '')
        doi_url = raw_url if raw_url else (f"https://doi.org/{raw_doi}" if raw_doi else "")

        return {
            "title": clean_bibtex_string(entry.get('title', 'Unknown Title')),
            "author": clean_bibtex_string(entry.get('author', 'Unknown Author')),
            "venue": clean_bibtex_string(entry.get('journal', '') or entry.get('booktitle', '')),
            "doi_url": doi_url,
            "year": clean_bibtex_string(entry.get('year', '0000')),
            "month": clean_bibtex_string(entry.get('month', ''))
        }
    except Exception as e:
        print(f"Bibtex 解析错误: {e}")
        return {}


def crop_and_save_image(src_path, dest_path, target_width=500, target_height=300):
    """等比缩放图片以填满目标尺寸，并居中裁剪超出部分"""
    try:
        if not src_path.exists():
            return False

        PIC_DEST_DIR.mkdir(parents=True, exist_ok=True)

        with Image.open(src_path) as img:
            # 转换为RGB格式以防PNG透明通道导致保存JPEG报错
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')

            # ImageOps.fit 完美实现“等比拉伸填满并居中裁剪”
            # centering=(0.5, 0.5) 代表从中心点向外裁剪
            img_cropped = ImageOps.fit(
                img,
                (target_width, target_height),
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5)
            )

            img_cropped.save(dest_path)
            return True
    except Exception as e:
        print(f"图片处理失败 {src_path}: {e}")
        return False


def process_md_files():
    results = []

    if not PAPERS_DIR.exists():
        print(f"目录不存在: {PAPERS_DIR}")
        return results

    for md_file in PAPERS_DIR.rglob("*.md"):
        try:
            post = frontmatter.load(md_file)
            metadata = post.metadata

            # 修复tags提取：兼容 tag 和 tags 键，确保转换为列表
            raw_tags = metadata.get('tags') or metadata.get('tag') or []
            if isinstance(raw_tags, str):
                tags = [t.strip() for t in raw_tags.split(',')]
            else:
                tags = [str(t) for t in raw_tags]

            # 1. 过滤：只提取 tags 中包含 directional 的 md 文件
            if not any('directional' in t.lower() for t in tags):
                continue

            # 提取 frontmatter 的属性到 properties
            properties = {
                "tags": tags,
                "teaser": metadata.get('teaser', ''),
                "code": metadata.get('code', ''),
                "project": metadata.get('project', ''),
                "slide": metadata.get('slide', ''),
                "supplemental": metadata.get('supplemental', '')
            }

            bibtex_raw = ""
            bibtex_parsed = {}
            match = re.search(r'```ad-cite\s+(.*?)```', post.content, re.DOTALL)
            if match:
                bibtex_raw = match.group(1).strip()
                bibtex_parsed = parse_bibtex(bibtex_raw)

            # 图片处理逻辑
            pic_dest_rel_path = ""
            if properties['teaser']:
                src_pic = PIC_SRC_DIR / properties['teaser']

                # --- 新增检查与打印逻辑 ---
                if not src_pic.exists():
                    print(f"⚠️ 图片未找到，请检查路径是否正确: {src_pic}")
                else:
                    dest_pic_name = f"{md_file.stem}_{properties['teaser']}"
                    dest_pic = PIC_DEST_DIR / dest_pic_name

                    if crop_and_save_image(src_pic, dest_pic):
                        pic_dest_rel_path = f".img/{dest_pic_name}"

            paper_info = {
                "filename": md_file.name,
                "properties": properties,
                "bibtex_raw": bibtex_raw,
                "bibtex_parsed": bibtex_parsed,
                "pic_path": pic_dest_rel_path
            }

            results.append(paper_info)
            print(f"成功处理文件: {md_file.name}")

        except Exception as e:
            print(f"处理文件 {md_file.name} 时出错: {e}")

    return results


def generate_readme(data):
    # 按照年份倒序排序 (如果年份无法转为整数则默认0)
    def sort_key(item):
        year_str = item.get("bibtex_parsed", {}).get("year", "0")
        return int(year_str) if year_str.isdigit() else 0

    data.sort(key=sort_key, reverse=True)

    lines = [
        "# A Survey on Work Related to Direction Field",
        "This repository contains a list of related work on **direction field**. \n\n"
        "It is currently a work in progress and is updated daily via **GitHub Actions**, which syncs with my personal database. And I will continue to maintain and expand this list regularly.\n\n"
        ":clap: If you have any suggestions or would like to contribute, please feel free to open an issue or contact me.\n\n"
        "| Teaser | Information |",
        "| :--- | :--- |"
    ]

    for item in data:
        bib = item.get('bibtex_parsed', {})
        props = item.get('properties', {})

        # 处理左栏：图片
        pic_md = f"<img src='{item['pic_path']}' width='500' height='300' style='object-fit: cover;'>" if item['pic_path'] else "No Image"

        # 处理右栏：信息
        title = f"**{bib.get('title', 'Unknown Title')}**"
        author = bib.get('author', 'Unknown Author')

        # 将 tags 列表转化为 `tag0`, `tag1` ... 的格式
        tags_list = props.get('tags', [])
        tags_str = " ".join([f"`{t.strip()}`" for t in tags_list])

        # 发表日期与期刊
        date_str = f"{bib.get('year', '')} {bib.get('month', '')}".strip()
        venue = bib.get('venue', '')
        date_venue = f"{date_str}{', ' + venue if venue else ''}"

        # 生成按钮链接
        links = []
        if bib.get('doi_url'): links.append(f"[[doi]]({bib.get('doi_url')})")
        if props.get('code'): links.append(f"[[code]]({props.get('code')})")
        if props.get('project'): links.append(f"[[project]]({props.get('project')})")
        if props.get('slide'): links.append(f"[[slide]]({props.get('slide')})")
        if props.get('supp'): links.append(f"[[supplemental]]({props.get('supplemental')})")
        links_str = " &nbsp; ".join(links)

        # 拼接表格行 (<br>换行)
        info_md = f"{title}<br>{author}<br>{date_venue}<br><br>tags: {tags_str}<br>{links_str}"
        lines.append(f"| {pic_md} | {info_md} |")

    with open(README_PATH, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


if __name__ == "__main__":
    print("开始处理论文数据...")
    extracted_data = process_md_files()

    with open(JSON_OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(extracted_data, f, ensure_ascii=False, indent=4)

    print(f"数据提取完成，共 {len(extracted_data)} 篇，开始生成 README.md...")
    generate_readme(extracted_data)
    print("README.md 生成完成！")