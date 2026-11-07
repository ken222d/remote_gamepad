# 各スクリプトから source する。個人の設定 remote_gamepad.env (git の対象外) を読む。
# source ではなく KEY=VALUE として読む (PowerShell と同じファイルを共有し、中身を実行しないため)
# すでに同名の環境変数があればそちらを優先する
CONFIG="$DIR/remote_gamepad.env"
if [ -f "$CONFIG" ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%$'\r'}"  # Windows で編集したとき (CRLF)
    [[ "$line" =~ ^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*=[[:space:]]*\"?([^\"]*)\"?[[:space:]]*$ ]] || continue
    key="${BASH_REMATCH[1]}"
    if [ -z "${!key+x}" ]; then export "$key=${BASH_REMATCH[2]}"; fi
  done < "$CONFIG"
fi

# require 変数名 説明: 未設定か見本の x のままなら、設定方法を表示して終了する
require() {
  local value="${!1:-}"
  if [ -z "$value" ] || [[ "$value" == *x* ]]; then
    echo "$1 ($2) が設定されていません。" >&2
    if [ -f "$CONFIG" ]; then
      echo "$CONFIG の $1= を書き換えてください。" >&2
    else
      echo "cp $DIR/remote_gamepad.env.example $CONFIG で作り、$1= を書き換えてください。" >&2
    fi
    exit 1
  fi
}
