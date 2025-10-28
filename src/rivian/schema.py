"""Minimal GraphQL schema for testing and DSL usage."""

RIVIAN_SCHEMA = """
scalar GenericScalar

type Query {
  currentUser: User
  getChargingSchedules(vehicleId: String!): ChargingSchedulesResponse
  getRegisteredWallboxes: [Wallbox]
  getTrailerProfiles(vehicleId: String!): [TrailerProfile]
  getVehicle(id: String!): Vehicle
  getVehicleMobileImages(resolution: String, extension: String, version: String): [VehicleImage]
  getVehicleOrderMobileImages(resolution: String, extension: String, version: String): [VehicleImage]
  planTrip2(
    waypoints: [RequestWaypointInput!]!
    vehicle: String!
    startingSoc: Float
    startingRangeMeters: Float
    targetArrivalSocPercent: Float
    driveMode: DriveMode
    networkPreferences: [NetworkPreference!]
    trailerProfile: TripPlanTrailerProfile
    hasAdapter: Boolean
  ): PlanTrip2Response

  # User & Referrals (from iOS app traffic)
  getReferralCode: ReferralCodeResponse
  getInvitationsByUser: [UserInvitation]

  # Vehicle Services (vs/gql-gateway endpoint)
  getAppointments(vehicleId: String!): ServiceAppointmentsResponse
  getActiveRequests(vehicleId: String!): ServiceRequestsResponse
  getProvisionedUsersForVehicle(vehicleId: String!): ProvisionedUsersResponse

  # Content Services (gql/content/graphql endpoint)
  chatSession(vehicleId: String): ChatSession

  placeholder: String
}

type Mutation {
  createCsrfToken: CreateCSRFTokenResponse
  createSigningChallenge(vehicleId: String!, deviceId: String!): SigningChallengeResponse
  deleteTrip(tripId: String!): DeleteTripResponse
  disenrollPhone(attrs: DisenrollPhoneInput!): DisenrollPhoneResponse
  enableCcc(vehicleId: String!, deviceId: String!): EnableCccResponse
  enrollInSmartCharging(vehicleId: String!, utilityId: String!, tariffId: String, location: InputGeoCoordinates!): SmartChargingEnrollmentResponse
  enrollPhone(attrs: EnrollPhoneInput!): EnrollPhoneResponse
  login(email: String!, password: String!): LoginResponse
  loginWithOTP(email: String!, otpToken: String!, otpCode: String!): LoginResponse
  parseAndShareLocationToVehicle(str: String!, vehicleId: String!): ShareLocationResponse
  saveTrip(tripId: String!, name: String!): SaveTripResponse
  sendVehicleCommand(attrs: SendVehicleCommandInput!): SendVehicleCommandResponse
  sendVehicleOperation(vehicleId: String!, payload: String!): SendVehicleOperationResponse
  sharePlaceIdToVehicle(placeId: String!, vehicleId: String!): ShareLocationResponse
  unenrollFromSmartCharging(vehicleId: String!): SmartChargingEnrollmentResponse
  updateDepartureSchedule(input: DepartureScheduleInput!): UpdateDepartureScheduleResponse
  updatePinToGear(vehicleId: String!, trailerId: String!, pinned: Boolean!): UpdatePinToGearResponse
  updateTrip(tripId: String!, input: UpdateTripInput!): UpdateTripResponse
  upgradeKeyToWCC2(vehicleId: String!, deviceId: String!): UpgradeKeyResponse
  verifySigningChallenge(vehicleId: String!, deviceId: String!, challengeId: String!, signature: String!): VerifyChallengeResponse
  sendParallaxPayload(payload: String!, meta: ParallaxMeta!): ParallaxResponse

  # Notifications (from iOS app traffic)
  registerNotificationTokens(tokens: [NotificationTokenInput!]!): NotificationResponse
  registerPushNotificationToken(token: String!, platform: String!, vehicleId: String): NotificationResponse
  liveNotificationRegisterStartToken(vehicleId: String!, token: String!): NotificationResponse
}

type Subscription {
  gearGuardRemoteConfig(vehicleId: String!): GearGuardConfig
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

union SendVehicleOperationResponse = SendVehicleOperationSuccess

type SendVehicleOperationSuccess {
  success: Boolean!
}

type ParseAndShareLocationToVehicleResponse {
  publishResponse: PublishResponse
}

type PublishResponse {
  result: Int
}

type Wallbox {
  wallboxId: String
  userId: String
  wifiId: String
  name: String
  linked: Boolean
  latitude: Float
  longitude: Float
  chargingStatus: String
  power: Float
  currentVoltage: Float
  currentAmps: Float
  softwareVersion: String
  model: String
  serialNumber: String
  maxAmps: Float
  maxVoltage: Float
  maxPower: Float
}

type Vehicle {
  id: String!
  vin: String
  invitedUsers: [InvitedUser]
  chargingSchedules: [ChargingSchedule]
  trailerProfiles: TrailerProfiles
}

union InvitedUser = ProvisionedUser | UnprovisionedUser

type ProvisionedUser {
  firstName: String
  lastName: String
  email: String
  roles: [String]
  userId: String
  devices: [UserDevice]
}

type UnprovisionedUser {
  email: String
  inviteId: String
  status: String
}

type UserDevice {
  type: String
  mappedIdentityId: String
  id: String
  hrid: String
  deviceName: String
  isPaired: Boolean
  isEnabled: Boolean
}

type VehicleImage {
  orderId: String
  vehicleId: String
  url: String
  extension: String
  resolution: String
  size: String
  design: String
  placement: String
  overlays: [VehicleImageOverlay]
}

type VehicleImageOverlay {
  url: String
  overlay: String
  zIndex: Int
}

type User {
  id: String!
  firstName: String
  lastName: String
  email: String
  emailVerified: Boolean
  primaryPhone: UserPhone
  settings: UserSettings
  vehicles: [UserVehicle]
  registrationChannels: [RegistrationChannel]
  enrolledPhones: [UserEnrolledPhone]
  pendingInvites: [UserInvitation]
  address: UserAddress
}

type UserPhone {
  countryCode: String
  formatted: String
  phone: String
  national: String
}

type UserSettings {
  distanceUnit: SettingValue
  temperatureUnit: SettingValue
  pressureUnit: SettingValue
}

type SettingValue {
  value: String
}

type UserVehicle {
  id: String!
  vin: String!
  name: String
  owner: String
  state: String
  createdAt: String
  updatedAt: String
  roles: [String]
  vas: UserVehicleAccess
  vehicle: VehicleDetails
  settings: UserVehicleSettingsMap
}

type UserVehicleAccess {
  vasVehicleId: String
  vehiclePublicKey: String
}

type VehicleDetails {
  id: String
  vin: String
  modelYear: Int
  make: String
  model: String
  expectedBuildDate: String
  plannedBuildDate: String
  expectedGeneralAssemblyStartDate: String
  actualGeneralAssemblyDate: String
  vehicleState: VehicleState
  mobileConfiguration: VehicleMobileConfiguration
}

type VehicleState {
  supportedFeatures: [SupportedFeature]
}

type SupportedFeature {
  name: String
  status: String
}

type VehicleMobileConfiguration {
  trimOption: VehicleMobileConfigurationOption
  exteriorColorOption: VehicleMobileConfigurationOption
  interiorColorOption: VehicleMobileConfigurationOption
}

type VehicleMobileConfigurationOption {
  optionId: String
  optionName: String
}

type UserVehicleSettingsMap {
  name: NameSetting
}

type NameSetting {
  value: String
}

type RegistrationChannel {
  type: String
}

type UserEnrolledPhone {
  vas: UserEnrolledPhoneAccess
  enrolled: [UserEnrolledPhoneEntry]
}

type UserEnrolledPhoneAccess {
  vasPhoneId: String
  publicKey: String
}

type UserEnrolledPhoneEntry {
  deviceType: String
  deviceName: String
  vehicleId: String
  identityId: String
  shortName: String
}

type UserInvitation {
  id: String
  invitedByFirstName: String
  role: String
  status: String
  vehicleId: String
  vehicleModel: String
  email: String
}

type UserAddress {
  country: String
}

type ChargingSchedulesResponse {
  schedules: [DepartureSchedule]
  smartChargingEnabled: Boolean
  vehicleId: String
}

type DepartureSchedule {
  id: String
  name: String
  enabled: Boolean
  days: [String]
  departureTime: String
  cabinPreconditioning: Boolean
  cabinPreconditioningTemp: Float
  targetSOC: Int
  offPeakHoursOnly: Boolean
  location: ScheduleLocation
}

type ScheduleLocation {
  latitude: Float
  longitude: Float
  radius: Float
}

input DepartureScheduleInput {
  vehicleId: String!
  scheduleId: String
  name: String!
  enabled: Boolean!
  days: [String!]!
  departureTime: String!
  cabinPreconditioning: Boolean
  cabinPreconditioningTemp: Float
  targetSOC: Int
  offPeakHoursOnly: Boolean
  location: ScheduleLocationInput
}

input ScheduleLocationInput {
  latitude: Float!
  longitude: Float!
  radius: Float!
}

type UpdateDepartureScheduleResponse {
  success: Boolean!
  schedule: DepartureSchedule
}

type SmartChargingEnrollmentResponse {
  success: Boolean!
  enrolled: Boolean
  message: String
}

type ShareLocationResponse {
  publishResponse: PublishResponse
}

type TrailerProfile {
  id: String!
  name: String!
  length: Float
  width: Float
  height: Float
  weight: Float
  trailerType: String
  pinnedToGear: Boolean
  createdAt: String
  updatedAt: String
}

type UpdatePinToGearResponse {
  success: Boolean!
  profile: TrailerProfile
}

type GearGuardConfig {
  enabled: Boolean
  videoMode: String
  recordingQuality: String
  streamingAvailable: Boolean
  storageRemaining: Float
  lastEventTimestamp: String
}

input TripPlanInput {
  vehicleId: String!
  waypoints: [WaypointInput!]!
  options: TripPlanOptions
}

input WaypointInput {
  latitude: Float!
  longitude: Float!
  name: String
}

input TripPlanOptions {
  avoidTolls: Boolean
  avoidHighways: Boolean
  minChargingSOC: Int
  targetArrivalSOC: Int
}

type TripPlanResponse {
  tripId: String!
  totalDistance: Float
  totalDuration: Int
  estimatedEnergyUsed: Float
  waypoints: [PlannedWaypoint]
  chargingStops: [PlannedChargingStop]
}

type PlannedWaypoint {
  sequence: Int
  location: TripLocation
  arrivalSOC: Int
  departureSOC: Int
  chargingRequired: Boolean
  chargingDuration: Int
  estimatedArrivalTime: String
}

type PlannedChargingStop {
  location: TripLocation
  arrivalSOC: Int
  targetSOC: Int
  chargingDuration: Int
  estimatedArrivalTime: String
}

type TripLocation {
  latitude: Float
  longitude: Float
  name: String
  address: String
  chargerId: String
}

type SaveTripResponse {
  success: Boolean!
  savedTrip: SavedTrip
}

type SavedTrip {
  id: String!
  name: String!
  createdAt: String
  updatedAt: String
  vehicleId: String
}

input UpdateTripInput {
  name: String
  waypoints: [WaypointInput!]
}

type UpdateTripResponse {
  success: Boolean!
  trip: SavedTrip
}

type DeleteTripResponse {
  success: Boolean!
}

type SigningChallengeResponse {
  challenge: String!
  challengeId: String!
  expiresAt: String
}

type VerifyChallengeResponse {
  success: Boolean!
  verified: Boolean
  message: String
}

type EnableCccResponse {
  success: Boolean!
  enabled: Boolean
  cccVersion: String
}

type UpgradeKeyResponse {
  success: Boolean!
  upgraded: Boolean
  wccVersion: String
}

# Parallax Protocol Support

input ParallaxMeta {
  vehicleId: String!
  model: String!
  isVehicleModelOp: Boolean!
  requiresWakeup: Boolean!
}

type ParallaxResponse {
  success: Boolean!
  sequenceNumber: Int
  payload: String
}

# Charging Schedule Types (from Android app)

type ChargingSchedule {
  startTime: String
  duration: Int
  location: GeoCoordinate
  amperage: Int
  enabled: Boolean
  weekDays: [String]
}

type GeoCoordinate {
  latitude: Float!
  longitude: Float!
}

input InputGeoCoordinates {
  latitude: Float!
  longitude: Float!
}

type TrailerProfiles {
  trailerDefault: TrailerProfile
  trailer1: TrailerProfile
  trailer2: TrailerProfile
  trailer3: TrailerProfile
}

# Trip Planning Types (from Android app)

enum DriveMode {
  CONSERVE
  SPORT
  ALL_PURPOSE
}

enum TripPlanTrailerProfile {
  NONE
  DEFAULT
  CUSTOM_1
  CUSTOM_2
  CUSTOM_3
}

input NetworkPreference {
  networkId: String!
  preference: String!
}

input RequestWaypointInput {
  latitude: Float!
  longitude: Float!
}

type PlanTrip2Response {
  plans: [TripPlan]
  status: String
}

type TripPlan {
  planIdentifierMetadata: PlanIdentifierMetadata
  driveLegs: [DriveLeg]
  waypoints: [TripWaypoint]
  batteryEmptyLocation: BatteryEmptyLocation
  summary: TripSummary
}

type PlanIdentifierMetadata {
  planId: String
  abrpRouteId: String
}

type DriveLeg {
  distanceMeters: Float
  durationSeconds: Int
  energyConsumptionKwh: Float
  polyline5: String
}

type TripWaypoint {
  waypointType: String
  requestWaypointsIndex: Int
  charger: ChargerInfo
  latitude: Float
  longitude: Float
  totalTimeAtWaypointSeconds: Int
  arrivalSOCPercent: Float
  arrivalRangeMeters: Float
  arrivalEnergyKwh: Float
  targetArrivalSocPercent: Float
  arrivalTimeUTC: String
  departureSOCPercent: Float
  departureRangeMeters: Float
  departureEnergyKwh: Float
  departureTimeUTC: String
  distanceFromOriginMeters: Float
  distanceToDestinationMeters: Float
  isSystemAdded: Boolean
}

type ChargerInfo {
  adapterRequired: Boolean
  entityId: String
  name: String
  maxPowerKw: Float
  chargeDurationSeconds: Int
}

type BatteryEmptyLocation {
  latitude: Float
  longitude: Float
  distanceToDestinationMeters: Float
}

type TripSummary {
  destinationReachable: Boolean
  socBelowLimitAtDestination: Boolean
  totalChargeDurationSeconds: Int
  totalDriveDurationSeconds: Int
  totalDriveDistanceMeters: Float
  totalTripDurationSeconds: Int
  arrivalSOCPercent: Float
  arrivalRangeMeters: Float
  arrivalEnergyKwh: Float
}

# New Types from iOS App Traffic Analysis

# User & Referrals
type ReferralCodeResponse {
  code: String
  url: String
  referralCode: String
}

# Vehicle Services Types
type ServiceAppointmentsResponse {
  appointments: [ServiceAppointment]
}

type ServiceAppointment {
  id: String
  vehicleId: String
  status: String
  scheduledTime: String
  serviceType: String
  location: ServiceLocation
  notes: String
  createdAt: String
  updatedAt: String
}

type ServiceLocation {
  name: String
  address: String
  city: String
  state: String
  zipCode: String
  latitude: Float
  longitude: Float
}

type ServiceRequestsResponse {
  requests: [ServiceRequest]
}

type ServiceRequest {
  id: String
  vehicleId: String
  status: String
  description: String
  category: String
  priority: String
  createdAt: String
  updatedAt: String
  assignedTo: String
}

# Provisioned Users
type ProvisionedUsersResponse {
  users: [ProvisionedVehicleUser]
}

type ProvisionedVehicleUser {
  userId: String!
  firstName: String
  lastName: String
  email: String
  roles: [String]
  status: String
  inviteStatus: String
  devices: [UserDevice]
  createdAt: String
  acceptedAt: String
}

# Content/Chat Types
type ChatSession {
  sessionId: String
  active: Boolean
  status: String
  createdAt: String
  messages: [ChatMessage]
}

type ChatMessage {
  id: String
  content: String
  sender: String
  timestamp: String
  type: String
}

# Notification Types
input NotificationTokenInput {
  token: String!
  platform: String!
  deviceId: String
  appVersion: String
}

type NotificationResponse {
  success: Boolean!
  message: String
  registeredTokens: [String]
  errors: [NotificationError]
}

type NotificationError {
  token: String
  error: String
  code: String
}
"""
