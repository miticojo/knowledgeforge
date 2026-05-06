import { NextResponse } from "next/server";

export async function GET() {
  return NextResponse.json({
    firebaseApiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY || "",
    firebaseAuthDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN || "",
    firebaseProjectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID || "",
    allowedEmails: process.env.NEXT_PUBLIC_ALLOWED_EMAILS || "",
  });
}
