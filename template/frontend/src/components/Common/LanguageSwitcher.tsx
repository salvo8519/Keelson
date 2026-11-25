// Keelstone: choose the language of the interface; it is also saved in the user's profile, so
// that API messages and emails use it.
import { UsersService } from "@/client"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { isLoggedIn } from "@/hooks/useAuth"
import { currentLanguage, LANGUAGES, setLanguage, t } from "@/i18n"

export function LanguageSwitcher() {
  if (LANGUAGES.length < 2) {
    return null
  }
  const change = async (code: string) => {
    if (isLoggedIn()) {
      try {
        await UsersService.updateCurrentUser({ body: { locale: code } })
      } catch {
        // The interface still switches; the profile keeps its previous language.
      }
    }
    setLanguage(code)
  }
  return (
    <div className="px-2 group-data-[collapsible=icon]:hidden">
      <Select value={currentLanguage()} onValueChange={change}>
        <SelectTrigger className="w-full" aria-label={t("Language")}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {LANGUAGES.map((language) => (
            <SelectItem key={language.code} value={language.code}>
              {language.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}

export default LanguageSwitcher
