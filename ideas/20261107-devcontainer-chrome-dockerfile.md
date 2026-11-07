# Chrome を Dockerfile でイメージに焼き込む

状態: **不採用**（2026-11-07。上司判断）

## 案
`.devcontainer/Dockerfile` を作り、Google Chrome を `apt` でイメージ作成時に入れる。
`postCreateCommand` から `playwright install --with-deps chrome` と `yarn.list` の無効化を外す。
（Node が Feature で後から入るため、Playwright 経由ではなく Google 公式パッケージを直接入れる想定）

## 背景
rebuild が遅かった。原因の推測は、`.venv`/`node_modules` を空のボリュームから入れ直したことと、
`postCreateCommand` で毎回走る `playwright install --with-deps chrome`。

## 得るもの・失うもの
- 得る: 設定だけの rebuild で Chrome のダウンロードと `apt` 導入が走らない
- 失う: Dockerfile が増える。Chrome のバージョンがイメージ作成時点で固定される

## 不採用の理由
Chrome は `postCreateCommand` で毎回入れる現状のままで足りる。rebuild の遅さは許容し、構成を増やさない。
（理由の詳細は上司から聞いていないため、「現状維持」という判断のみ記録）

## 再検討の目安
rebuild の頻度が上がり、待ち時間が負担になったとき。その前に、各工程の所要時間を `time` で測ること。
