import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"

import {
  type Body_auth_login as AccessToken,
  AuthService,
  type UserCreate,
  type UserRead,
  UsersService,
} from "@/client"
import { currentLanguage, isSupported, setLanguage } from "@/i18n"
import { session } from "@/lib/session"
import { handleError } from "@/utils"
import useCustomToast from "./useCustomToast"

const isLoggedIn = () => {
  return session.accessToken() !== null
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
    mutationFn: (data: UserCreate) => AuthService.register({ body: data }),
    onSuccess: () => {
      navigate({ to: "/login" })
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] })
    },
  })

  // Keelson: returns true when the user's saved language differs from the interface's; the
  // page is then reloaded in that language.
  const login = async (data: AccessToken): Promise<boolean> => {
    const response = await AuthService.login({
      body: data,
    })
    session.signIn(response.data.access_token, response.data.refresh_token)
    const { locale } = (await UsersService.readCurrentUser()).data
    if (isSupported(locale) && locale !== currentLanguage()) {
      setLanguage(locale, { reload: false })
      return true
    }
    return false
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

  const logout = () => {
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

export { isLoggedIn }
export default useAuth
