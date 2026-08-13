# tg-social-media-download-bot

paste media and post to telegram

## feature

two main features:

- [x] parse instagram links

  > now supported

- [ ] ~~auto send liked post to group~~

  > how bypass instagram bot detection

## deploy

```bash
# load cookie from browser
# or login by `uv run instaloader --login YOUR-USERNAME`
$ uv run instaloader --load-cookies firefox

# copy ~/.config/instaloader/session-* file to vps
# or direct run
$ uv run main.py
```
