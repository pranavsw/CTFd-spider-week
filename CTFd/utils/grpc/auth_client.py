import grpc
from . import authentication_pb2
from . import authentication_pb2_grpc
import logging

class AuthenticationClient:
    def __init__(self, host='localhost', port=50051, use_ssl=False):
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self.channel = None
        self.stub = None
        self._connect()

    def _connect(self):
        """Establish connection to gRPC server"""
        try:
            if self.use_ssl:
                # For secure connection (HTTPS)
                credentials = grpc.ssl_channel_credentials()
                self.channel = grpc.secure_channel(
                    f'{self.host}:{self.port}', 
                    credentials
                )
            else:
                # For non-secure connection (HTTP)
                self.channel = grpc.insecure_channel(f'{self.host}:{self.port}')
            
            self.stub = authentication_pb2_grpc.AuthenticationStub(self.channel)
            # Test connection
            grpc.channel_ready_future(self.channel).result(timeout=5)
            logging.info(f"Successfully connected to gRPC server at {self.host}:{self.port}")
        except grpc.FutureTimeoutError as e:
            logging.error(f"Timeout connecting to gRPC server at {self.host}:{self.port}: {e}")
            raise
        except Exception as e:
            logging.error(f"Failed to connect to gRPC server at {self.host}:{self.port}: {e}")
            raise

    def generate_otp(self, client_id: str, client_secret: str, roll_no: int):
        try:
            if not self.stub:
                self._connect()
            
            # Ensure client_id and client_secret are properly formatted strings
            client_id = str(client_id).strip()
            client_secret = str(client_secret).strip()
            
            # Debug logging
            logging.info(f"Attempting OTP generation for roll_no: {roll_no}")
            logging.debug(f"Client ID length: {len(client_id)}")
            logging.debug(f"Client Secret length: {len(client_secret)}")
            
            request = authentication_pb2.GenerateOTPRequest(
                clientID=client_id,
                clientSecret=client_secret,
                rollNo=roll_no
            )
            
            response = self.stub.GenerateOTP(request)
            return True, response.message
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.PERMISSION_DENIED:
                logging.error(f"Authentication failed - Invalid credentials")
                return False, "Invalid Client ID or Client Secret. Please check your configuration."
            logging.error(f"gRPC error in generate_otp: {e}")
            return False, f"gRPC error: {str(e)}"
        except Exception as e:
            logging.error(f"Unexpected error in generate_otp: {e}")
            return False, f"Unexpected error: {str(e)}"

    def verify_otp(self, client_id: str, client_secret: str, roll_no: int, otp: int):
        try:
            request = authentication_pb2.VerifyOTPRequest(
                clientID=client_id,
                clientSecret=client_secret,
                rollNo=roll_no,
                otp=otp
            )
            response = self.stub.VerifyOTP(request)
            return True, response.message, response.Details
        except grpc.RpcError as e:
            return False, f"gRPC error: {str(e)}", None

    def close(self):
        self.channel.close()