"""Minimal GraphQL schema for testing and DSL usage."""

RIVIAN_SCHEMA = """
scalar GenericScalar

type Query {
  placeholder: String
}

type Mutation {
  createCsrfToken: CreateCSRFTokenResponse
  login(email: String!, password: String!): LoginResponse
  loginWithOTP(email: String!, otpToken: String!, otpCode: String!): LoginResponse
  disenrollPhone(attrs: DisenrollPhoneInput!): DisenrollPhoneResponse
  enrollPhone(attrs: EnrollPhoneInput!): EnrollPhoneResponse
  sendVehicleCommand(attrs: SendVehicleCommandInput!): SendVehicleCommandResponse
  parseAndShareLocationToVehicle(str: String!, vehicleId: String!): ParseAndShareLocationToVehicleResponse
}

type CreateCSRFTokenResponse {
  csrfToken: String!
  appSessionToken: String!
}

union LoginResponse = MobileLoginResponse | MobileMFALoginResponse

type MobileLoginResponse {
  accessToken: String!
  refreshToken: String!
  userSessionToken: String!
}

type MobileMFALoginResponse {
  otpToken: String!
}

input DisenrollPhoneInput {
  enrollmentId: String!
}

type DisenrollPhoneResponse {
  success: Boolean!
}

input EnrollPhoneInput {
  userId: String!
  vehicleId: String!
  publicKey: String!
  type: String!
  name: String!
}

type EnrollPhoneResponse {
  success: Boolean!
}

input SendVehicleCommandInput {
  command: String!
  hmac: String!
  timestamp: String!
  vasPhoneId: String!
  deviceId: String!
  vehicleId: String!
  params: GenericScalar
}

type SendVehicleCommandResponse {
  id: String
  command: String
  state: String
}

type ParseAndShareLocationToVehicleResponse {
  publishResponse: PublishResponse
}

type PublishResponse {
  result: Int
}
"""
