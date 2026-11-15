# d2-arch-diagram

AWS の構成図を D2 の書き方で書き、公式アイコン入りの SVG にするツールと、Claude Code のスキル。配置・配線・ラベルの位置は決まった計算で決まり、同じ入力からは同じ SVG が出る。

AWS（Amazon Web Services）とも、D2 の開発元の Terrastruct とも関係のない個人のツールです。

## 必要なもの

Docker。初回の実行時に `docker/Dockerfile` からイメージを作る（数十秒）。そのとき、次の場所からダウンロードする。

- AWS の公式アイコン配布物（`d1.awsstatic.com`）
- フォント BIZ UDPGothic（`raw.githubusercontent.com`）
- npm のパッケージ（libavoid-js、puppeteer-core）と Alpine のパッケージ（Chromium など）

## Claude Code のスキルとして使う

```sh
git clone https://github.com/naru-rama/d2-arch-diagram.git ~/.claude/skills/aws-diagram
```

あとは Claude Code に AWS の構成図を頼めば、このスキルが使われる。手順と描き方の決まりは `SKILL.md`、入力の書き方は `reference.md` にある。

## コマンドとして使う

```sh
bin/aws-diagram render examples/web-app.d2   # 同じフォルダに web-app.svg と確認用の web-app.png
bin/aws-diagram icons lambda                 # 使えるアイコン名を探す
tests/run.sh                                 # 見本の図が変わっていないか確かめる
```

## ライセンス

このリポジトリのコードは MIT ライセンス。実行時に取ってくるものは、それぞれの条件に従う。

- AWS の公式アイコン: [AWS Architecture Icons](https://aws.amazon.com/architecture/icons/) の条件。このリポジトリには含めていない。
- BIZ UDPGothic: SIL Open Font License 1.1。出力する SVG には、使った文字だけを埋め込む。
- libavoid-js: LGPL-2.1。npm から取ってきて、そのまま使う。
