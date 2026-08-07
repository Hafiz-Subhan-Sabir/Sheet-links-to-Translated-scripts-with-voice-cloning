/** Mirrors backend YOUTUBE_POPULAR_LANGUAGES for translation pickers. */
export const YOUTUBE_POPULAR_LANGUAGES: { code: string; name: string }[] = [
  { code: "en", name: "English" },
  { code: "es", name: "Spanish" },
  { code: "hi", name: "Hindi" },
  { code: "pt", name: "Portuguese" },
  { code: "ar", name: "Arabic" },
  { code: "id", name: "Indonesian" },
  { code: "fr", name: "French" },
  { code: "ja", name: "Japanese" },
  { code: "de", name: "German" },
  { code: "ko", name: "Korean" },
  { code: "ru", name: "Russian" },
  { code: "tr", name: "Turkish" },
  { code: "vi", name: "Vietnamese" },
  { code: "it", name: "Italian" },
  { code: "bn", name: "Bengali" },
  { code: "ur", name: "Urdu" },
  { code: "tl", name: "Filipino" },
  { code: "zh-CN", name: "Chinese (Simplified)" },
  { code: "zh-TW", name: "Chinese (Traditional)" },
  { code: "pl", name: "Polish" },
  { code: "nl", name: "Dutch" },
  { code: "th", name: "Thai" },
  { code: "fa", name: "Persian" },
  { code: "ms", name: "Malay" },
  { code: "ta", name: "Tamil" },
  { code: "te", name: "Telugu" },
  { code: "uk", name: "Ukrainian" },
  { code: "el", name: "Greek" },
  { code: "he", name: "Hebrew" },
  { code: "sv", name: "Swedish" },
  { code: "ro", name: "Romanian" },
  { code: "cs", name: "Czech" },
  { code: "hu", name: "Hungarian" },
  { code: "pa", name: "Punjabi" },
  { code: "mr", name: "Marathi" },
  { code: "gu", name: "Gujarati" },
  { code: "kn", name: "Kannada" },
  { code: "ml", name: "Malayalam" },
  { code: "sw", name: "Swahili" },
  { code: "af", name: "Afrikaans" },
  { code: "no", name: "Norwegian" },
  { code: "da", name: "Danish" },
  { code: "fi", name: "Finnish" },
];

export function normalizeLangCode(code: string): string {
  return code.toLowerCase().split("-")[0];
}

export function defaultTargetLanguages(sourceLanguage: string): string[] {
  const source = normalizeLangCode(sourceLanguage);
  return YOUTUBE_POPULAR_LANGUAGES.map((l) => l.code).filter(
    (code) => normalizeLangCode(code) !== source
  );
}
