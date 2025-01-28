import grpc
# from protos.authentication_pb2 import GenerateOTPRequest, VerifyOTPRequest
from CTFd.protos.authentication_pb2 import GenerateOTPRequest, VerifyOTPRequest
from CTFd.protos.authentication_pb2_grpc import AuthenticationStub

class OTPClient:
    def __init__(self, host='localhost', port=50051):
        self.channel = grpc.insecure_channel(f'{host}:{port}')
        self.stub = AuthenticationStub(self.channel)

    def generate_otp(self, client_id, client_secret, roll_no):
        request = GenerateOTPRequest(clientID=client_id, clientSecret=client_secret, rollNo=roll_no)
        return self.stub.GenerateOTP(request)

    def verify_otp(self, client_id, client_secret, roll_no, otp):
        request = VerifyOTPRequest(clientID=client_id, clientSecret=client_secret, rollNo=roll_no, otp=otp)
        return self.stub.VerifyOTP(request)