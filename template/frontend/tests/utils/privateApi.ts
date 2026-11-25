// Keelstone: test users are created through the public registration endpoint; the official
// template used a private endpoint that the Keelstone backend does not expose.
import { AuthService } from "../../src/client"
import { client } from "../../src/client/client.gen"

client.setConfig({
  baseURL: `${process.env.VITE_API_URL}`,
})

export const createUser = async ({
  email,
  password,
}: {
  email: string
  password: string
}) => {
  const user = { email, password, full_name: "Test User" }
  // Registration answers the same for every address (no account enumeration), so it does
  // not return the user: the helper returns what it registered.
  await AuthService.register({ body: user, throwOnError: true })
  return { email, full_name: user.full_name }
}
