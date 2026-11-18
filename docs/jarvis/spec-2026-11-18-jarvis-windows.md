# Goal
Make the Hassan web page (frontend/index.html, style.css, app.js, orb.js) look good on a phone (iPhone Safari), without changing how it looks on a laptop/desktop.

# Problem
On the phone, the status text ("Listening...") and Hassan's spoken replies end up inside or on top of the chat area, so they are hard to read. The page was designed for wide screens.

# Requirements
- Use a CSS media query for narrow screens (for example max-width: 700px) so the desktop layout stays exactly the same. Do not alter desktop styles.
- On narrow screens: orb and status text clearly visible at the top, the chat in its own scrollable area below it, the controls (mic button, EN/NL, hands-free, Send, text input) fixed at the bottom, no overlap, no horizontal scrolling.
- Add or check the viewport meta tag (width=device-width, initial-scale=1, viewport-fit=cover) and use safe-area insets for the iPhone notch and home bar. Use dvh units where needed so Safari's address bar does not cut things off.
- Touch targets at least 44px. Text readable (at least 16px in the input so Safari does not zoom).
- Do not touch server.py, brain.py, the .env or any permissions or settings files. Only edit files in frontend/.

# Acceptance checks
- Desktop layout unchanged (compare the CSS: all new rules are inside the narrow-screen media query).
- At a 390px wide viewport (use browser dev tools or a headless check if possible) there is no overlap and no horizontal scroll.
- Commit with a clear message on a new branch named mobile-layout, not on master, so the user can review and merge or discard it. Never commit .env.
- Finish with a short summary of what changed.