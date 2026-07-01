# Command Centre → APK setup

Three things need to happen: (1) make the site installable (PWA), (2) push those
files to your `command-centre` repo, (3) generate the APK. Your new-tools problem
solves itself once step 1 is done right — see the note at the bottom.

## 1. Add these files to your `pixelprotech-za.github.io/command-centre` repo

- `manifest.json` — tells Android this is an installable app (name, icon, colors)
- `service-worker.js` — caches the page so it opens even with no signal, but
  always checks the live site first
- Two lines in `<head>` of your `index.html`:

```html
<link rel="manifest" href="/command-centre/manifest.json">
<meta name="theme-color" content="#040406">
```

- Just before `</body>` in `index.html`, add:

```html
<script>
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/command-centre/service-worker.js');
}
</script>
```

## 2. Make three icon files

You need `icon-192.png`, `icon-512.png`, and `icon-512-maskable.png` (square,
transparent-safe background since maskable icons get cropped into a circle on
some phones). Drop them in the same folder as `manifest.json`. Any square PNG
of your logo works — I can generate these for you if you want, just say so.

## 3. Push to GitHub Pages

Commit and push like you normally do. Once live, open
`https://pixelprotech-za.github.io/command-centre/` on your phone in Chrome —
you should see "Add to Home Screen" / an install prompt appear. That confirms
the PWA part works.

## 4. Generate the actual APK — no SDK needed

Go to **https://www.pwabuilder.com**, paste in:

```
https://pixelprotech-za.github.io/command-centre/
```

It scans the manifest + service worker, scores your PWA, then lets you
click **Package for Stores → Android → Generate**. It builds a signed `.apk`
(and `.aab` if you ever want the Play Store) and gives you a download link.
That `.apk` file is what you WhatsApp/AirDrop/USB-transfer to any Android
phone — they tap it, allow "install from unknown sources" once, and it's
on their home screen like a real app.

## The "new tools" answer

Because the APK is a thin wrapper (a WebView pointed at your live URL, per
the manifest `start_url`), **you don't rebuild the APK every time you add a
tool.** You just push the new card to `command-centre` on GitHub Pages like
you already do. Everyone who has the APK installed sees the new tool the
next time they open the app — no reinstall needed.

You only need to regenerate and redistribute the APK if you change the app
**icon** or **name**, since those get baked in at build time.
