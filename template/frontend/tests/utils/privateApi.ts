// Keelson: test users are created through the public registration endpoint; the official
// template used a private endpoint that the Keelson backend does not expose.
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
  const response = await AuthService.register({
    body: {
      email,
      password,
      full_name: "Test User",
    },
  })
  return response.data
}
