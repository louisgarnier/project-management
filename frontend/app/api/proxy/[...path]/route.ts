import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

const ts = () => new Date().toISOString().replace("T", " ").substring(0, 23);

async function proxy(request: NextRequest, params: { path: string[] }): Promise<NextResponse> {
  const endpoint = "/" + params.path.join("/");
  const searchParams = request.nextUrl.searchParams.toString();
  const fullPath = searchParams ? `${endpoint}?${searchParams}` : endpoint;
  const method = request.method;
  const contentType = request.headers.get("content-type") || "";
  const isMultipart = contentType.includes("multipart/form-data");

  console.log(`${ts()} 📡 [Frontend→API] ${method} ${fullPath}`);

  try {
    let headers: Record<string, string>;
    let body: string | ArrayBuffer | undefined;

    if (isMultipart) {
      // Forward Content-Type as-is (includes the boundary) and body as raw bytes
      headers = { "Content-Type": contentType };
      body = await request.arrayBuffer();
    } else {
      headers = { "Content-Type": "application/json" };
      if (method !== "GET" && method !== "HEAD") {
        body = await request.text();
      }
    }

    const response = await fetch(`${BACKEND_URL}${fullPath}`, {
      method,
      headers,
      body,
    });

    console.log(`${ts()} ✅ [Frontend→API] ${method} ${fullPath} → ${response.status}`);
    if (response.status === 204) {
      return new NextResponse(null, { status: 204 });
    }

    // Pass non-JSON responses (markdown exports, file downloads, etc.) through
    // verbatim — preserve Content-Type AND Content-Disposition so the browser
    // triggers a save dialog instead of treating the body as JSON.
    const upstreamCT = response.headers.get("content-type") || "";
    if (!upstreamCT.includes("application/json")) {
      const bytes = await response.arrayBuffer();
      const passthrough = new Headers();
      if (upstreamCT) passthrough.set("Content-Type", upstreamCT);
      const cd = response.headers.get("content-disposition");
      if (cd) passthrough.set("Content-Disposition", cd);
      return new NextResponse(bytes, { status: response.status, headers: passthrough });
    }

    const data = await response.json().catch(() => null);
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    console.error(`${ts()} ❌ [Frontend→API] ${method} ${fullPath} error:`, error);
    return NextResponse.json({ error: "Backend unavailable" }, { status: 503 });
  }
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  return proxy(request, await params);
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  return proxy(request, await params);
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  return proxy(request, await params);
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  return proxy(request, await params);
}
