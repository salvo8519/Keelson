// Keelson: the token of a new or rotated key, shown once.
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { useCopyToClipboard } from "@/hooks/useCopyToClipboard"

interface ShowTokenProps {
  token: string | null
  onClose: () => void
}

export function ShowToken({ token, onClose }: ShowTokenProps) {
  const [copied, copy] = useCopyToClipboard()
  return (
    <Dialog open={token !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Store this key now</DialogTitle>
          <DialogDescription>
            This is the only time the key is shown. Send it in the X-API-Key
            header.
          </DialogDescription>
        </DialogHeader>
        <code
          className="break-all rounded-md bg-muted p-3 text-sm"
          data-testid="api-key-token"
        >
          {token}
        </code>
        <DialogFooter>
          <Button variant="outline" onClick={() => token && copy(token)}>
            {copied ? "Copied" : "Copy"}
          </Button>
          <Button onClick={onClose}>Done</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default ShowToken
