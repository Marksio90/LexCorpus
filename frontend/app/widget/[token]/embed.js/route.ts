import { NextRequest } from "next/server";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ token: string }> },
) {
  const { token } = await params;
  const config = await prisma.widgetConfig.findUnique({
    where:  { token },
    select: { enabled: true, accentColor: true, title: true },
  });

  if (!config || !config.enabled) {
    return new Response("// Widget not found", {
      status: 404,
      headers: { "Content-Type": "application/javascript" },
    });
  }

  const base = process.env.NEXTAUTH_URL;
  if (!base) {
    return new Response("// Widget misconfigured: NEXTAUTH_URL not set", {
      status: 500,
      headers: { "Content-Type": "application/javascript" },
    });
  }
  const accent = config.accentColor;
  const title  = config.title.replace(/`/g, "\\`");

  const js = `
(function () {
  if (window.__lexcorpus_widget) return;
  window.__lexcorpus_widget = true;

  var BASE  = ${JSON.stringify(base)};
  var TOKEN = ${JSON.stringify(token)};
  var ACCENT = ${JSON.stringify(accent)};
  var TITLE  = \`${title}\`;

  /* Floating button */
  var btn = document.createElement("button");
  btn.id = "lc-widget-btn";
  btn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="none" viewBox="0 0 24 24" stroke="white" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-3 3v-3z"/></svg>';
  btn.title = TITLE;
  Object.assign(btn.style, {
    position: "fixed", bottom: "24px", right: "24px",
    width: "56px", height: "56px", borderRadius: "50%",
    background: ACCENT, border: "none", cursor: "pointer",
    display: "flex", alignItems: "center", justifyContent: "center",
    boxShadow: "0 4px 20px rgba(0,0,0,.2)", zIndex: "2147483640",
    transition: "transform .15s",
  });
  btn.onmouseenter = function() { btn.style.transform = "scale(1.08)"; };
  btn.onmouseleave = function() { btn.style.transform = "scale(1)"; };
  document.body.appendChild(btn);

  /* Iframe container */
  var container = document.createElement("div");
  container.id = "lc-widget-container";
  Object.assign(container.style, {
    position: "fixed", bottom: "92px", right: "24px",
    width: "380px", height: "560px", maxHeight: "calc(100vh - 110px)",
    borderRadius: "20px", overflow: "hidden",
    boxShadow: "0 8px 40px rgba(0,0,0,.2)", zIndex: "2147483639",
    display: "none", border: "1px solid rgba(0,0,0,.08)",
  });

  var iframe = document.createElement("iframe");
  iframe.src = BASE + "/widget/" + TOKEN;
  iframe.style.cssText = "width:100%;height:100%;border:none;display:block;";
  iframe.allow = "clipboard-write";
  container.appendChild(iframe);
  document.body.appendChild(container);

  var open = false;
  btn.addEventListener("click", function () {
    open = !open;
    container.style.display = open ? "block" : "none";
    btn.innerHTML = open
      ? '<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" fill="none" viewBox="0 0 24 24" stroke="white" stroke-width="2.5"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/></svg>'
      : '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="none" viewBox="0 0 24 24" stroke="white" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-3 3v-3z"/></svg>';
  });
})();
`.trim();

  return new Response(js, {
    headers: {
      "Content-Type":  "application/javascript; charset=utf-8",
      "Cache-Control": "public, max-age=60",
    },
  });
}
