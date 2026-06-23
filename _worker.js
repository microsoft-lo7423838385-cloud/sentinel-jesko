export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // Captcha challenge page at /redirect
    if (url.pathname === '/redirect') {
      return new Response(getCaptchaHTML(), {
        headers: { 'Content-Type': 'text/html;charset=utf-8' }
      });
    }

    // Turnstile verification endpoint
    if (url.pathname === '/verify' && request.method === 'POST') {
      const formData = await request.formData();
      const token = formData.get('turnstile_token');

      if (!token) {
        return new Response('Missing token. <a href="/redirect">Try again</a>.', {
          headers: { 'Content-Type': 'text/html;charset=utf-8' }
        });
      }

      const verifyRes = await fetch(
        'https://challenges.cloudflare.com/turnstile/v0/siteverify',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: new URLSearchParams({
            secret: env.TURNSTILE_SECRET,
            response: token
          })
        }
      );

      const result = await verifyRes.json();

      if (result.success) {
        return Response.redirect('https://departmentallaw.com', 302);
      } else {
        return new Response('Captcha failed. <a href="/redirect">Try again</a>.', {
          headers: { 'Content-Type': 'text/html;charset=utf-8' }
        });
      }
    }

    return new Response('Not found', { status: 404 });
  }
};

function getCaptchaHTML() {
  return `<!DOCTYPE html>
<html>
<head>
  <title>Verification</title>
  <script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>
</head>
<body style="font-family:system-ui,-apple-system,sans-serif;display:flex;justify-content:center;align-items:center;height:100vh;margin:0;background:#0a0a0a;color:#fff;">
  <div style="text-align:center;max-width:360px;padding:24px;">
    <h2>Verify you are human</h2>
    <p>Click the checkbox below to continue to departmentallaw.com</p>
    <form action="/verify" method="POST">
      <div class="cf-turnstile"
           data-sitekey="0x4AAAAAADpQj7lel83BYsN4"
           data-callback="onSuccess"
           data-theme="dark"></div>
    </form>
    <script>
      function onSuccess(token) {
        document.querySelector('form').submit();
      }
    </script>
  </div>
</body>
</html>`;
}
