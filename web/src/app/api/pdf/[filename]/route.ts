import { NextRequest } from "next/server";
import { API_BASE as API_URL } from "@/lib/api";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ filename: string }> }
) {
  const { filename } = await params;
  const res = await fetch(`${API_URL}/api/papers/downloads/${encodeURIComponent(filename)}`);

  if (!res.ok) {
    return new Response("PDF not found", { status: 404 });
  }

  const blob = await res.blob();
  return new Response(blob, {
    headers: {
      "Content-Type": "application/pdf",
      "Content-Disposition": "inline",
    },
  });
}
