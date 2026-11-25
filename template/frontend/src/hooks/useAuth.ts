import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"

import {
  type Body_auth_login as AccessToken,
  AuthService,
  type UserRead,
  type UserRegister,
  UsersService,
} from "@/client"
import { currentLanguage, isSupported, setLanguage } from "@/i18n"
import { session } from "@/lib/session"
import { handleError } from "@/utils"
import useCustomToast from "./useCustomToast"

const isLoggedIn = () => {
  return session.isSignedIn()
}

// Keelson: completes a sign-in (password or single sign-on) once the API has set the session
// cookies. Returns true when the user's saved language differs from the interface's; the page
// is then reloaded in it.
const completeSignIn = async (): Promise<boolean> => {
  session.markSignedIn()
  const { locale } = (await UsersService.readCurrentUser()).data
  if (isSupported(locale) && locale !== currentLanguage()) {
    setLanguage(locale, { reload: false })
    return true
  }
  return false
}

const useAuth = () => {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { showErrorToast } = useCustomToast()

  const { data: user } = useQuery<UserRead | null, Error>({
    queryKey: ["currentUser"],
    queryFn: async () => (await UsersService.readCurrentUser()).data,
    enabled: isLoggedIn(),
  })

  const signUpMutation = useMutation({
    mutationFn: (data: UserRegister) => AuthService.register({ body: data }),
    onSuccess: () => {
      navigate({ to: "/login" })
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] })
    },
  })

  const login = async (data: AccessToken): Promise<boolean> => {
    // The API sets the session cookies; the tokens in the body are for programs.
    await AuthService.login({ body: data })
    return completeSignIn()
  }

  const loginMutation = useMutation({
    mutationFn: login,
    onSuccess: (languageChanged) => {
      if (languageChanged) {
        window.location.assign("/")
      } else {
        navigate({ to: "/" })
      }
    },
    onError: handleError.bind(showErrorToast),
  })

  const logout = async () => {
    await AuthService.endSession().catch(() => undefined)
    session.signOut()
    queryClient.clear()
    navigate({ to: "/login" })
  }

  return {
    signUpMutation,
    loginMutation,
    logout,
    user,
  }
}

export { completeSignIn, isLoggedIn }
export default useAuth
