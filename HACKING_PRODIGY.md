#

<https://chatgpt.com/share/69861a46-7dac-8012-9929-33e8b61f10b9>

unminified bundle from prodigy 1.18.4 is here [bundle.unminified.js](./bundle.unminified.js)

replace like this

```sh
mv ../.venv/lib/python3.12/site-packages/prodigy/static/bundle.js ../.venv/lib/python3.12/site-packages/prodigy/static/bundle.js.orig
cp ../../bundle.unminified.js ../.venv/lib/python3.12/site-packages/prodigy/static/bundle.js
```
