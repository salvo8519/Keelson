import { toast } from "sonner"
import { t } from "@/i18n"

const useCustomToast = () => {
  const showSuccessToast = (description: string) => {
    toast.success(t("Success!"), {
      description,
    })
  }

  const showErrorToast = (description: string) => {
    toast.error(t("Something went wrong!"), {
      description,
    })
  }

  return { showSuccessToast, showErrorToast }
}

export default useCustomToast
