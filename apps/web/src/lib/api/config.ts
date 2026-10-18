export const DEFAULT_API_URL = "http://localhost:8000/api/v1";

export const API_BASE_URL = (process.env.NEXT_PUBLIC_SIDE_API_URL || DEFAULT_API_URL).replace(/\/+$/, "");

export const IS_MOCK = process.env.NEXT_PUBLIC_SIDE_MOCK === "1" || process.env.NEXT_PUBLIC_SIDE_MOCK === "true";
