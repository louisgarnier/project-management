import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

const ts = () => new Date().toISOString().replace("T", " ").substring(0, 23);

async function proxy(
  request: NextRequest,
  params: { path: string[] }
): Promise<NextResponse> {
  const endpoint = "/" + params.path.join("/");
  const searchParams = request.nextUrl.searchParams.toString();
  const fullPath = searchParams ? `${endpoint}?${searchParams}` : endpoint;
  const method = request.method;

  console.log(`${ts()} 📡 [Frontend→API] ${method} ${fullPath}`);

  try {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };

    let body: string | undefined;
    if (method !== "GET" && method !== "HEAD") {
      body = await request.text();
    }

    const response = await fetch(`${BACKEND_URL}${fullPath}`, {
      method,
      headers,
      body,
    });

    const data = await response.json().catch(() => null);
    console.log(
      `${ts()} ✅ [Frontend→API] ${method} ${fullPath} → ${response.status}`
    );
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
