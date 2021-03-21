import { SERVICE_TO_SERVICE_SECRET, USERS_SERVICE } from "../config";
import { GraphQLClient, gql } from "graphql-request";
import jwt from "jsonwebtoken";

const USERS_SERVICE_INTERNAL_API_ENDPOINT = `${USERS_SERVICE}/internal-api`;

export type User = {
  id: number;
  email: string;
  isStaff: boolean;
};

export const fetchUserInfo = async (id: string): Promise<User> => {
  const token: string = jwt.sign({}, SERVICE_TO_SERVICE_SECRET!, {
    issuer: "gateway",
    audience: "users-service",
    expiresIn: "1m",
    notBefore: 0,
  });

  const client = new GraphQLClient(USERS_SERVICE_INTERNAL_API_ENDPOINT, {
    headers: {
      "x-service-token": token,
    },
  });

  const query = gql`
    query($id: ID) {
      user(id: $id) {
        id
        email
        isStaff
      }
    }
  `;

  const data = await client.request(query, { id });
  return data.user as User;
};
